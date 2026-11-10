"""Aggregations over routing events. Estimated and measured values are separate series."""

import math
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Model,
    PrivacyFinding,
    RoutingAttempt,
    RoutingEvent,
    ScoredOutcome,
)


def percentile(values: list[float], q: float) -> float | None:
    """Linear-interpolated percentile (matches numpy's default)."""
    if not values:
        return None
    data = sorted(values)
    pos = (len(data) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return data[lo] + (data[hi] - data[lo]) * (pos - lo)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _events(db: Session, user_id: str | None) -> list[RoutingEvent]:
    query = select(RoutingEvent).order_by(RoutingEvent.created_at)
    if user_id is not None:
        query = query.where(RoutingEvent.user_id == user_id)
    return list(db.scalars(query))


def _kinds(db: Session) -> dict[str, str]:
    return {m.slug: m.kind for m in db.scalars(select(Model))}


def _outcomes(db: Session, event_ids: list[str]) -> dict[str, ScoredOutcome]:
    if not event_ids:
        return {}
    rows = db.scalars(select(ScoredOutcome).where(ScoredOutcome.event_id.in_(event_ids)))
    return {row.event_id: row for row in rows}


def summary(db: Session, user_id: str | None) -> dict:
    events = _events(db, user_id)
    kinds = _kinds(db)
    answered = [e for e in events if e.status == "succeeded"]
    abstained = [e for e in events if e.abstained]
    failed = [e for e in events if e.status == "failed"]
    ids = [e.id for e in events]
    attempts = (
        list(db.scalars(select(RoutingAttempt).where(RoutingAttempt.event_id.in_(ids))))
        if ids
        else []
    )
    local = [e for e in answered if kinds.get(e.selected_model or "") == "local"]
    outcomes = _outcomes(db, [e.id for e in answered])
    quality = [o.quality for o in outcomes.values() if o.quality is not None]
    gen = [e.generation_latency_ms for e in answered if e.generation_latency_ms is not None]
    ttft = [e.ttft_ms for e in answered if e.ttft_ms is not None]
    routing = [e.routing_latency_ms for e in events if e.routing_latency_ms is not None]
    return {
        "requests": len(events),
        "answered": len(answered),
        "abstained": len(abstained),
        "failed": len(failed),
        "abstention_rate": len(abstained) / len(events) if events else None,
        "local_share": len(local) / len(answered) if answered else None,
        "measured": {
            "total_cost_usd": sum(e.measured_cost_usd or 0.0 for e in answered),
            "mean_cost_usd": _mean([e.measured_cost_usd or 0.0 for e in answered]),
            "latency_p50_ms": percentile(gen, 0.5),
            "latency_p95_ms": percentile(gen, 0.95),
            "ttft_p50_ms": percentile(ttft, 0.5),
            "ttft_p95_ms": percentile(ttft, 0.95),
        },
        "estimated": {
            "mean_cost_usd": _mean([e.estimated_cost_usd or 0.0 for e in answered]),
            "mean_input_tokens": _mean(
                [float(e.estimated_input_tokens) for e in answered if e.estimated_input_tokens]
            ),
        },
        "routing_overhead": {
            "p50_ms": percentile(routing, 0.5),
            "p95_ms": percentile(routing, 0.95),
            "target_ms": 500,
        },
        "attempt_failures": sum(1 for a in attempts if a.status not in {"ok", "blocked"}),
        "blocked_attempts": sum(1 for a in attempts if a.status == "blocked"),
        "quality_mean": _mean(quality),
        "scored_outcomes": len(outcomes),
    }


def by_model(db: Session, user_id: str | None) -> list[dict]:
    events = [e for e in _events(db, user_id) if e.selected_model]
    outcomes = _outcomes(db, [e.id for e in events])
    groups: dict[str, list[RoutingEvent]] = defaultdict(list)
    for event in events:
        groups[event.selected_model].append(event)  # type: ignore[index]
    kinds = _kinds(db)
    result = []
    for model, rows in sorted(groups.items()):
        ok = [e for e in rows if e.status == "succeeded"]
        quality = [
            outcomes[e.id].quality
            for e in rows
            if e.id in outcomes and outcomes[e.id].quality is not None
        ]
        result.append(
            {
                "model": model,
                "kind": kinds.get(model),
                "requests": len(rows),
                "succeeded": len(ok),
                "failed": len(rows) - len(ok),
                "measured_mean_cost_usd": _mean([e.measured_cost_usd or 0.0 for e in ok]),
                "estimated_mean_cost_usd": _mean([e.estimated_cost_usd or 0.0 for e in rows]),
                "measured_latency_p50_ms": percentile(
                    [e.generation_latency_ms for e in ok if e.generation_latency_ms], 0.5
                ),
                "quality_mean": _mean(quality),
            }
        )
    return result


def by_task(db: Session, user_id: str | None) -> list[dict]:
    events = [e for e in _events(db, user_id) if e.task_type]
    outcomes = _outcomes(db, [e.id for e in events])
    kinds = _kinds(db)
    groups: dict[str, list[RoutingEvent]] = defaultdict(list)
    for event in events:
        groups[event.task_type].append(event)  # type: ignore[index]
    result = []
    for task, rows in sorted(groups.items()):
        ok = [e for e in rows if e.status == "succeeded"]
        quality = [
            outcomes[e.id].quality
            for e in rows
            if e.id in outcomes and outcomes[e.id].quality is not None
        ]
        result.append(
            {
                "task": task,
                "requests": len(rows),
                "abstained": sum(1 for e in rows if e.abstained),
                "local_share": (
                    sum(1 for e in ok if kinds.get(e.selected_model or "") == "local") / len(ok)
                    if ok
                    else None
                ),
                "measured_mean_cost_usd": _mean([e.measured_cost_usd or 0.0 for e in ok]),
                "measured_latency_p50_ms": percentile(
                    [e.generation_latency_ms for e in ok if e.generation_latency_ms], 0.5
                ),
                "quality_mean": _mean(quality),
            }
        )
    return result


def cost_latency(db: Session, user_id: str | None, limit: int = 200) -> list[dict]:
    """Per-request points; estimated and measured are separate fields (never merged)."""
    events = [e for e in _events(db, user_id) if e.status == "succeeded"][-limit:]
    return [
        {
            "event_id": e.id,
            "model": e.selected_model,
            "estimated_cost_usd": e.estimated_cost_usd,
            "measured_cost_usd": e.measured_cost_usd,
            "estimated_latency_ms": e.estimated_latency_ms,
            "measured_latency_ms": e.generation_latency_ms,
        }
        for e in events
    ]


def privacy(db: Session, user_id: str | None) -> dict:
    events = _events(db, user_id)
    ids = [e.id for e in events]
    findings: Counter = Counter()
    if ids:
        for row in db.scalars(select(PrivacyFinding).where(PrivacyFinding.event_id.in_(ids))):
            findings[row.entity_type] += row.count
    reasons: Counter = Counter()
    for event in events:
        if event.abstained and event.abstain_reason:
            for part in event.abstain_reason.split("; "):
                reasons[part.split(":", 1)[-1]] += 1
    attempts = (
        list(db.scalars(select(RoutingAttempt).where(RoutingAttempt.event_id.in_(ids))))
        if ids
        else []
    )
    return {
        "findings_by_type": dict(findings),
        "abstain_reasons": dict(reasons),
        "egress_blocked": sum(1 for a in attempts if a.status == "blocked"),
        "labels": dict(Counter(e.effective_label for e in events if e.effective_label)),
    }
