"""Turns a chat request + DB state into pipeline inputs, and persists the outcome.

Steps 3-8 of the workflow (label, evidence, detect, payload, estimate) live here;
the pipeline handles eligibility onward.
"""

import asyncio
import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.context.builder import build_context
from app.context.compress import CompressionNotice, compress_history
from app.context.token_count import count_messages, count_text
from app.core.config import Settings
from app.db.models import (
    BudgetLedger,
    ChatSession,
    Chunk,
    ConsentRecord,
    Document,
    InstitutionalPolicyRecord,
    Message,
    Model,
    ModelHealth,
    ModelPrice,
    PrivacyFinding,
    ProviderConnection,
    RoutingAttempt,
    RoutingEvent,
    UserModelPref,
)
from app.documents.chunk import DocumentChunk
from app.documents.classify import classify_task
from app.documents.retrieve import Retriever
from app.gateway.factory import BlockedAdapter, build_cloud_adapter, build_local_adapter
from app.gateway.pipeline import PipelineCandidate, PipelineRequest
from app.privacy.consent import Consent
from app.privacy.detector import PrivacyScanner
from app.privacy.gate import check_outbound, redact, serialize_payload
from app.privacy.labels import highest_label
from app.privacy.policy import InstitutionalPolicy
from app.registry.models import HealthState, ModelSpec, PriceSnapshot
from app.routing.config import routing_config
from app.routing.features import Features

HISTORY_KEEP = 4
HEALTH_STALE_S = 300  # failures older than this are ignored for cloud models
TOP_K = 4


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=100_000)
    task: str | None = None
    cost_preference: Literal["lowest", "balanced", "best"] = "balanced"


@dataclass
class Prepared:
    request: PipelineRequest
    candidates: list[PipelineCandidate]
    effective_label: str
    findings: list[dict]
    evidence_refs: list[dict]
    compression: CompressionNotice | None
    connection_by_model: dict[str, str] = field(default_factory=dict)
    local_slugs: set[str] = field(default_factory=set)


def _summarize(turns: list[dict[str, str]]) -> str:
    """Local extractive summary: no model call, so nothing leaves the host."""
    parts = [f"{t['role']}: {t['content'][:160].strip()}" for t in turns]
    return "Earlier conversation (summarised locally): " + " | ".join(parts)


def _institutional(db: Session) -> InstitutionalPolicy:
    record = db.scalar(select(InstitutionalPolicyRecord))
    if record is None:
        return InstitutionalPolicy()
    return InstitutionalPolicy(
        allow_cloud=record.allow_cloud,
        forbid_labels=frozenset(item for item in record.forbid_labels.split(",") if item),
    )


def _latest_price(db: Session, model_id: str) -> PriceSnapshot | None:
    row = db.scalar(
        select(ModelPrice)
        .where(ModelPrice.model_id == model_id)
        .order_by(ModelPrice.captured_at.desc())
        .limit(1)
    )
    if row is None:
        return None
    return PriceSnapshot(
        row.input_per_mtok, row.output_per_mtok, row.captured_at.isoformat(), row.source
    )


def _health_stats(db: Session, model_id: str) -> tuple[HealthState | None, tuple[float, float]]:
    rows = list(
        db.scalars(
            select(ModelHealth)
            .where(ModelHealth.model_id == model_id)
            .order_by(ModelHealth.ts.desc())
            .limit(20)
        )
    )
    if not rows:
        return None, (0.0, 0.0)
    latest = rows[0]
    stamp = latest.ts if latest.ts.tzinfo else latest.ts.replace(tzinfo=UTC)
    stale = (datetime.now(UTC) - stamp).total_seconds() > HEALTH_STALE_S
    latencies = [row.p50_ms for row in rows if row.p50_ms is not None]
    ewma = 0.0
    for value in reversed(latencies):
        ewma = value if ewma == 0.0 else 0.7 * ewma + 0.3 * value
    failure_rate = sum(1 for row in rows if not row.ok) / len(rows)
    # A recorded failure expires so a recovered provider is retried; until then it is skipped.
    state = HealthState(
        ok=True if (stale and not latest.ok) else latest.ok,
        p50_ms=latest.p50_ms,
        error_rate=failure_rate,
    )
    return state, (ewma, failure_rate)


def month_spend(db: Session, connection_id: str) -> float:
    now = datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = db.scalar(
        select(func.coalesce(func.sum(BudgetLedger.usd), 0.0)).where(
            BudgetLedger.connection_id == connection_id,
            BudgetLedger.kind == "settle",
            BudgetLedger.ts >= start,
        )
    )
    return float(total or 0.0)


def _find_consent(
    db: Session, user_id: str, session_id: str, slug: str, payload_hash: str
) -> Consent | None:
    record = db.scalar(
        select(ConsentRecord).where(
            ConsentRecord.user_id == user_id,
            ConsentRecord.session_id == session_id,
            ConsentRecord.destination_model_id == slug,
            ConsentRecord.payload_hash == payload_hash,
            ConsentRecord.revoked_at.is_(None),
            ConsentRecord.expires_at > datetime.now(UTC),
        )
    )
    if record is None:
        return None
    return Consent(
        record.user_id,
        record.session_id,
        record.destination_model_id,
        record.payload_hash,
        record.expires_at,
        record.revoked_at,
    )


def _spec(model: Model) -> ModelSpec:
    return ModelSpec(
        model.slug,
        model.kind,  # type: ignore[arg-type]
        model.provider,
        model.context_limit,
        model.max_output,
        model.enabled,
        model.min_ram_gb,
        model.min_vram_gb,
    )


def _clean(messages: list[dict]) -> list[dict[str, str]]:
    return [{"role": m["role"], "content": m["content"]} for m in messages]


def prepare_turn(
    db: Session,
    user_id: str,
    session: ChatSession,
    payload: ChatRequest,
    settings: Settings,
    scanner: PrivacyScanner | None = None,
) -> Prepared:
    scanner = scanner or PrivacyScanner()
    cfg = routing_config().get("routing", {})
    reserved_output = int(cfg.get("reserved_output_tokens", 512))

    # 3-4. LABEL + EVIDENCE (local)
    doc_rows = list(db.scalars(select(Document).where(Document.session_id == session.id)))
    chunk_rows = (
        list(
            db.scalars(
                select(Chunk)
                .where(Chunk.document_id.in_([d.id for d in doc_rows]))
                .order_by(Chunk.document_id, Chunk.idx)
            )
        )
        if doc_rows
        else []
    )
    chunks = [DocumentChunk(c.id, c.text, c.page, c.idx, c.label) for c in chunk_rows]
    evidence = Retriever(chunks).search(payload.prompt, top_k=TOP_K) if chunks else []
    doc_label = highest_label(*[d.label for d in doc_rows]) if doc_rows else "public"
    history_rows = list(
        db.scalars(
            select(Message).where(Message.session_id == session.id).order_by(Message.created_at)
        )
    )
    history = [{"role": m.role, "content": m.content, "label": m.label} for m in history_rows]
    labels = [session.label, doc_label, *[e.chunk.label for e in evidence]]
    labels += [m["label"] for m in history]
    effective_label = highest_label(*labels)  # type: ignore[arg-type]

    # 5. DETECT (coarse findings only; no text is retained)
    findings: dict[tuple[str, str], int] = {}

    def scan(text: str, scope: str) -> None:
        result = scanner.scan(text, scope)
        for finding in result.findings:
            key = (scope, finding.entity_type)
            findings[key] = findings.get(key, 0) + finding.count

    scan(payload.prompt, "prompt")
    for item in evidence:
        scan(item.chunk.text, "chunk")
    for turn in history:
        scan(turn["content"], "history")

    # 6. PAYLOAD: compress older turns locally (summary inherits the highest label)
    compression = None
    turns = history
    if len(history) > HISTORY_KEEP:
        old_label = highest_label(*[m["label"] for m in history[:-HISTORY_KEEP]])
        turns, compression = compress_history(history, _summarize, old_label)
        effective_label = highest_label(effective_label, old_label)  # type: ignore[arg-type]
    turns = _clean(turns)
    evidence_text = [f"[p.{e.chunk.page}] {e.chunk.text}" for e in evidence]

    # candidates ------------------------------------------------------------
    institutional = _institutional(db)
    prefs = {
        pref.model_id: pref
        for pref in db.scalars(select(UserModelPref).where(UserModelPref.user_id == user_id))
        if pref.enabled
    }
    models = list(db.scalars(select(Model).where(Model.enabled.is_(True)).order_by(Model.slug)))
    candidates: list[PipelineCandidate] = []
    pre_removed: list[dict] = []
    stats: dict[str, tuple[float, float]] = {}
    connection_by_model: dict[str, str] = {}
    local_slugs: set[str] = set()
    fallback_input = 0
    for model in models:
        spec = _spec(model)
        context = build_context(
            payload.prompt,
            evidence_text,
            turns,
            tokenizer=model.tokenizer,
            reserved_output=min(reserved_output, model.max_output),
            context_limit=model.context_limit,
        )
        health, model_stats = _health_stats(db, model.id)
        stats[model.slug] = model_stats
        fallback_input = max(fallback_input, context.input_tokens)
        if model.kind == "local":
            local_slugs.add(model.slug)
            candidates.append(
                PipelineCandidate(
                    spec,
                    build_local_adapter(model, settings),
                    health=health,
                    messages=context.messages,
                    tier="local",
                    input_tokens=context.input_tokens,
                )
            )
            continue
        pref = prefs.get(model.id)
        connection = (
            db.scalar(
                select(ProviderConnection).where(
                    ProviderConnection.id == pref.connection_id,
                    ProviderConnection.user_id == user_id,
                )
            )
            if pref and pref.connection_id
            else None
        )
        if pref is None or connection is None:
            pre_removed.append({"model": model.slug, "reason": "no_provider_key"})
            continue
        connection_by_model[model.slug] = connection.id
        payload_bytes = serialize_payload(context.messages)
        consent = None
        first = check_outbound(
            payload_bytes,
            scanner=scanner,
            mode=session.mode,
            label=effective_label,
            user_id=user_id,
            session_id=session.id,
            model_id=model.slug,
            institutional=institutional,
        )
        if first.reason == "consent_required":
            consent = _find_consent(db, user_id, session.id, model.slug, first.payload_hash)

        def outbound(data: bytes, _slug: str = model.slug, _consent: Consent | None = consent):
            return check_outbound(
                data,
                scanner=scanner,
                mode=session.mode,
                label=effective_label,
                user_id=user_id,
                session_id=session.id,
                model_id=_slug,
                consent=_consent,
                institutional=institutional,
            )

        gate = outbound(payload_bytes)
        meta = {}
        if gate.reason == "consent_required":
            meta = {
                "preview": redact(payload_bytes.decode("utf-8"), scanner)[:4000],
                "label": effective_label,
            }
        budget = None
        if connection.monthly_budget_usd is not None:
            budget = max(0.0, connection.monthly_budget_usd - month_spend(db, connection.id))
        candidates.append(
            PipelineCandidate(
                spec,
                build_cloud_adapter(model, connection, settings)
                if gate.allowed
                else BlockedAdapter(),
                price=_latest_price(db, model.id),
                health=health or HealthState(ok=True),  # unknown cloud health: assume ok
                gate=gate,
                messages=context.messages,
                outbound_check=outbound,
                tier=pref.tier,
                input_tokens=context.input_tokens,
                budget_remaining_usd=budget,
                meta=meta,
            )
        )
        scan(payload_bytes.decode("utf-8"), "payload")

    # 10. FEATURES
    pages = len({e.chunk.page for e in evidence})
    task = (
        payload.task
        if payload.task and payload.task != "general"
        else classify_task(payload.prompt)
    )
    features = Features(
        task=task,
        input_tokens=fallback_input or count_messages([{"content": payload.prompt}]),
        evidence_chunks=len(evidence),
        evidence_spread=pages >= 3,
        mode=session.mode,
        cost_preference=payload.cost_preference,
        estimated_cost_usd=0.0,
        estimated_latency_ms=None,
        retrieval_margin=evidence[0].margin if evidence else 0.0,
        estimated_output_tokens=reserved_output,
        evidence_tokens=sum(count_text(e.chunk.text) for e in evidence),
        retrieval_top_score=evidence[0].score if evidence else 0.0,
        doc_pages=max((d.pages for d in doc_rows), default=0),
        history_turns=len(history),
        stats=stats,
    )
    request = PipelineRequest(
        prompt=payload.prompt,
        messages=_clean([{"role": "user", "content": payload.prompt}]),
        features=features,
        reserved_output=reserved_output,
        pre_removed=tuple(pre_removed),
    )
    return Prepared(
        request=request,
        candidates=candidates,
        effective_label=effective_label,
        findings=[
            {"scope": scope, "entity_type": kind, "count": count}
            for (scope, kind), count in sorted(findings.items())
        ],
        evidence_refs=[
            {"chunk_id": e.chunk.id, "page": e.chunk.page, "score": round(e.score, 3)}
            for e in evidence
        ],
        compression=compression,
        connection_by_model=connection_by_model,
        local_slugs=local_slugs,
    )


async def probe_local_health(
    candidates: list[PipelineCandidate], settings: Settings
) -> list[PipelineCandidate]:
    """Live-probe local hosts so an unreachable Ollama removes the local action."""
    result = []
    for candidate in candidates:
        if candidate.model.kind != "local":
            result.append(candidate)
            continue
        if settings.fake_providers:
            ok = True
        else:
            try:
                ok = await asyncio.wait_for(candidate.adapter.health(), timeout=3.0)
            except Exception:
                ok = False
        result.append(replace(candidate, health=HealthState(ok=ok)))
    return result


def persist_turn(
    db: Session,
    user_id: str,
    session: ChatSession,
    prepared: Prepared,
    records: dict,
    answer: str,
) -> RoutingEvent:
    route = records.get("route") or {}
    terminal = records.get("done") or records.get("abstain") or records.get("error") or {}
    if "abstain" in records:
        status = "abstained"
    elif "done" in records:
        status = "succeeded"
    else:
        status = "failed"
    removed = route.get("removed") or terminal.get("removed") or []
    features = prepared.request.features
    event = RoutingEvent(
        user_id=user_id,
        session_id=session.id,
        policy_name=route.get("policy", "fixed_rules"),
        policy_version=route.get("policy_version", "0"),
        selected_model=route.get("model"),
        rule_id=route.get("rule_id"),
        status=status,
        estimated_input_tokens=route.get("estimated_input_tokens"),
        estimated_output_tokens=route.get("estimated_output_tokens"),
        estimated_cost_usd=route.get("estimated_cost_usd"),
        estimated_latency_ms=route.get("estimated_latency_ms"),
        measured_input_tokens=terminal.get("input_tokens"),
        measured_output_tokens=terminal.get("output_tokens"),
        measured_cost_usd=terminal.get("measured_cost_usd"),
        routing_latency_ms=route.get("routing_latency_ms") or terminal.get("routing_latency_ms"),
        generation_latency_ms=terminal.get("generation_latency_ms"),
        ttft_ms=terminal.get("ttft_ms"),
        explanation=(route.get("reason") or terminal.get("suggestion") or "")[:500],
        task_type=features.task,
        features_json=json.dumps(features.to_log()),
        eligible_json=json.dumps(route.get("eligible", [])),
        removed_json=json.dumps(removed),
        shadow_json=json.dumps(route.get("shadow")) if route.get("shadow") else None,
        action_prob=route.get("probability"),
        abstained="abstain" in records,
        abstain_reason=("; ".join(f"{r['model']}:{r['reason']}" for r in removed))[:500]
        if "abstain" in records
        else None,
        effective_label=prepared.effective_label,
    )
    db.add(event)
    db.flush()
    for attempt in records.get("attempts", []):
        db.add(
            RoutingAttempt(
                event_id=event.id,
                model=attempt["model"],
                status=attempt["status"],
                error_class=attempt.get("error_class"),
                measured_cost_usd=attempt.get("cost_usd"),
                attempt_no=attempt["attempt_no"],
                input_tokens=attempt.get("input_tokens"),
                output_tokens=attempt.get("output_tokens"),
                latency_ms=attempt.get("latency_ms"),
                ttft_ms=attempt.get("ttft_ms"),
            )
        )
        connection_id = prepared.connection_by_model.get(attempt["model"])
        if attempt.get("cost_usd"):
            db.add(
                BudgetLedger(
                    connection_id=connection_id,
                    user_id=user_id,
                    event_id=event.id,
                    kind="settle",
                    usd=float(attempt["cost_usd"]),
                )
            )
        model = db.scalar(select(Model).where(Model.slug == attempt["model"]))
        if model is not None and attempt["status"] != "blocked":
            db.add(
                ModelHealth(
                    model_id=model.id,
                    ok=attempt["status"] == "ok",
                    p50_ms=attempt.get("latency_ms"),
                    err_rate=0.0 if attempt["status"] == "ok" else 1.0,
                )
            )
    for finding in prepared.findings:
        db.add(PrivacyFinding(event_id=event.id, detector_version="patterns-v1", **finding))
    if answer:
        db.add(
            Message(
                session_id=session.id,
                role="assistant",
                content=answer,
                label=prepared.effective_label,
                tokens=count_text(answer),
                event_id=event.id,
            )
        )
    db.commit()
    if status == "failed":
        from app.feedback.service import score_event  # R = -1 needs no quality signal

        score_event(db, event.id)
    return event
