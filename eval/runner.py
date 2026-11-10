"""Shared evaluation core: identical evidence, constraints and scoring for every policy."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from app.context.builder import build_context
from app.context.token_count import count_text
from app.documents.chunk import chunk_document
from app.documents.parse import parse_document
from app.documents.retrieve import Retriever
from app.feedback.scoring import automatic_score
from app.privacy.detector import PrivacyScanner
from app.privacy.gate import check_outbound, serialize_payload
from app.registry.models import HealthState, ModelSpec, PriceSnapshot
from app.routing.eligibility import eligible_candidates
from app.routing.features import Features, estimate_candidate
from app.routing.reward import FAILURE_REWARD, RewardConfig, reward

from eval.common import EvalItem, doc_text
from eval.executor import ModelProfile, Result

SCANNER = PrivacyScanner()
RESERVED_OUTPUT = 512


@dataclass
class PreparedItem:
    item: EvalItem
    features: Features
    messages: dict[str, list[dict[str, str]]]
    tokens: dict[str, int]
    evidence: list[str]
    gates: dict
    specs: dict[str, ModelSpec]


_RETRIEVERS: dict[str, tuple[Retriever, list]] = {}


def _retriever(dataset, doc_id: str):
    if doc_id not in _RETRIEVERS:
        parsed = parse_document(f"{doc_id}.txt", doc_text(dataset, doc_id).encode("utf-8"))
        chunks = chunk_document(parsed, words_per_chunk=120)
        _RETRIEVERS[doc_id] = (Retriever(chunks), chunks)
    return _RETRIEVERS[doc_id]


def prepare_item(
    item: EvalItem, dataset, profiles: dict[str, ModelProfile], mode: str = "cloud_allowed"
) -> PreparedItem:
    retriever, chunks = _retriever(dataset, item.doc_id)
    if item.task_type == "summary":
        step = max(1, len(chunks) // 6)
        picked = chunks[::step][:6]
        evidence = [c.text for c in picked]
        top, margin = 0.0, 0.0
    else:
        hits = retriever.search(item.prompt, top_k=4)
        evidence = [h.chunk.text for h in hits]
        top = hits[0].score if hits else 0.0
        margin = hits[0].margin if hits else 0.0
    pages = len({c.page for c in chunks})
    messages, tokens, specs, gates = {}, {}, {}, {}
    for slug, profile in profiles.items():
        context = build_context(
            item.prompt,
            evidence,
            [],
            tokenizer="fallback",
            reserved_output=min(RESERVED_OUTPUT, profile.max_output),
            context_limit=profile.context_limit,
        )
        messages[slug], tokens[slug] = context.messages, context.input_tokens
        specs[slug] = ModelSpec(
            slug,
            profile.kind,
            "eval",
            profile.context_limit,
            profile.max_output,  # type: ignore[arg-type]
        )
        if profile.kind == "cloud":
            gates[slug] = check_outbound(
                serialize_payload(context.messages),
                scanner=SCANNER,
                mode=mode,
                label=item.label,
                user_id="eval",
                session_id=item.doc_id,
                model_id=slug,
            )
    features = Features(
        task=item.task_type,
        input_tokens=max(tokens.values()),
        evidence_chunks=len(evidence),
        evidence_spread=len(chunks) > 8 and item.task_type != "summary" and len(evidence) >= 3,
        mode=mode,
        cost_preference="balanced",
        estimated_cost_usd=0.0,
        estimated_latency_ms=None,
        retrieval_margin=margin,
        estimated_output_tokens=RESERVED_OUTPUT,
        evidence_tokens=sum(count_text(e) for e in evidence),
        retrieval_top_score=top,
        doc_pages=pages,
        history_turns=0,
        tiers={slug: p.tier for slug, p in profiles.items()},
    )
    return PreparedItem(item, features, messages, tokens, evidence, gates, specs)


def eligibility(prep: PreparedItem, profiles: dict[str, ModelProfile]):
    estimates, prices, health = [], {}, {}
    for slug, profile in profiles.items():
        price = (
            PriceSnapshot(profile.price_in, profile.price_out, "eval", "profile")
            if profile.kind == "cloud"
            else None
        )
        prices[slug] = price
        health[slug] = HealthState(ok=True)
        estimates.append(
            estimate_candidate(
                prep.specs[slug],
                price,
                input_tokens=prep.tokens[slug],
                reserved_output=min(RESERVED_OUTPUT, profile.max_output),
            )
        )
    return eligible_candidates(estimates, prices=prices, health=health, gates=prep.gates)


def quality_of(item: EvalItem, text: str, evidence: list[str]) -> float | None:
    return automatic_score(
        item.task_type,
        text,
        references=item.references or None,
        evidence=evidence or None,
        key_points=item.key_points or None,
    )


@dataclass
class Outcome:
    record: dict = field(default_factory=dict)


def score_result(
    item: EvalItem, result: Result, evidence: list[str], cfg: RewardConfig
) -> tuple[float | None, float]:
    """(quality A, reward). Failures are R = -1 with their incurred cost kept."""
    if result.status != "ok":
        return None, FAILURE_REWARD
    quality = quality_of(item, result.text, evidence)
    quality = 0.0 if quality is None else quality
    return quality, reward(quality, result.cost_usd, result.latency_ms, cfg)


def run_item(
    prep: PreparedItem,
    policy,
    executor,
    profiles: dict[str, ModelProfile],
    cfg: RewardConfig,
    features: Features | None = None,
) -> dict:
    eligible, removed = eligibility(prep, profiles)
    item = prep.item
    base = {
        "item_id": item.item_id,
        "doc_id": item.doc_id,
        "split": item.split,
        "task": item.task_type,
        "kind": item.kind,
        "label": item.label,
        "policy": policy.name,
        "policy_version": policy.version,
        "removed": [{"model": r.model, "reason": r.reason} for r in removed],
    }
    if not eligible:
        return {
            **base,
            "abstained": True,
            "model": None,
            "reward": None,
            "quality": None,
            "cost": 0.0,
            "latency": None,
            "status": "abstained",
            "prob": None,
            "eligible": [],
            "features": prep.features.to_log(),
        }
    slugs = [e.estimate.model.slug for e in eligible]
    feats = features or prep.features
    try:
        decision = policy.select(feats, slugs)
    except ValueError:
        # e.g. strong_cloud_only when cloud is ineligible: under shared constraints it abstains
        return {
            **base,
            "abstained": True,
            "model": None,
            "reward": None,
            "quality": None,
            "cost": 0.0,
            "latency": None,
            "status": "abstained",
            "prob": None,
            "eligible": slugs,
            "features": prep.features.to_log(),
            "removed": base["removed"] + [{"model": "*", "reason": "policy_has_no_action"}],
        }
    if decision.action not in slugs:  # defensive; policies must never escape the eligible set
        raise AssertionError(f"{policy.name} chose ineligible {decision.action}")
    profile = profiles[decision.action]
    result = executor.run(
        item, profile, prep.messages[decision.action], prep.tokens[decision.action]
    )
    quality, value = score_result(item, result, prep.evidence, cfg)
    return {
        **base,
        "abstained": False,
        "model": decision.action,
        "prob": decision.probability,
        "distribution": decision.distribution,
        "rule_id": decision.rule_id,
        "eligible": slugs,
        "quality": quality,
        "reward": value,
        "cost": result.cost_usd,
        "latency": result.latency_ms,
        "ttft": result.ttft_ms,
        "status": result.status,
        "cached": result.cached,
        "features": feats.to_log(),
    }


def oracle_record(
    prep: PreparedItem, slug: str, executor, profile: ModelProfile, cfg: RewardConfig
) -> dict:
    """Outcome of one model on one item irrespective of policy (empirical oracle)."""
    item = prep.item
    result = executor.run(item, profile, prep.messages[slug], prep.tokens[slug])
    quality, value = score_result(item, result, prep.evidence, cfg)
    return {
        "item_id": item.item_id,
        "doc_id": item.doc_id,
        "split": item.split,
        "task": item.task_type,
        "kind": item.kind,
        "label": item.label,
        "model": slug,
        "quality": quality,
        "reward": value,
        "cost": result.cost_usd,
        "latency": result.latency_ms,
        "status": result.status,
        "features": prep.features.to_log(),
    }


def with_stats(features: Features, stats: dict[str, tuple[float, float]]) -> Features:
    return replace(features, stats=dict(stats))


# --- orchestration helpers ---------------------------------------------------------


def setup(dataset_name: str, executor_kind: str = "sim", seed: int = 0):
    """Return (dataset_dir, items, profiles, executor) for a named dataset."""
    from eval.common import CACHE, DATASETS, load_items
    from eval.executor import SIM_PROFILES, LiveExecutor, ResultCache, SimulatedExecutor

    dataset = DATASETS / dataset_name
    items = load_items(dataset)
    if executor_kind == "live":
        executor, profiles = LiveExecutor.from_config(dataset_name)
    else:
        profiles = dict(SIM_PROFILES)
        executor = SimulatedExecutor(seed, ResultCache(CACHE / f"sim-{dataset_name}"))
    return dataset, items, profiles, executor


class Handoff:
    """Production serving rule: fixed rules until the learned policy is ready (cold start)."""

    name = "adaptive_bandit"

    def __init__(self, learned, rules=None) -> None:
        from app.routing.rules import FixedRules

        self.learned = learned
        self.rules = rules or FixedRules()

    @property
    def version(self) -> str:
        return self.learned.version

    def select(self, features, eligible):
        if self.learned.ready:
            return self.learned.select(features, eligible)
        return self.rules.select(features, eligible)

    def update(self, batch):
        return Handoff(self.learned.update(batch), self.rules)
