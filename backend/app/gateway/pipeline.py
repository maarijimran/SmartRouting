"""End-to-end gateway pipeline (docs/01 steps 7-15) for one chat turn.

Pure with respect to I/O other than the adapters it is handed, so the same code
serves the API, the tests (fake adapters) and the evaluation replay engine.
"""

import time
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field, replace

from app.adapters.base import Adapter, AdapterError, GenerationParams
from app.gateway.egress import EgressBlocked, send
from app.privacy.gate import GateResult
from app.registry.models import HealthState, ModelSpec, PriceSnapshot
from app.routing.eligibility import eligible_candidates
from app.routing.features import Features, estimate_candidate
from app.routing.rules import Decision, FixedRules, Policy

ROUTING_TARGET_MS = 500


@dataclass(frozen=True)
class PipelineCandidate:
    model: ModelSpec
    adapter: Adapter
    price: PriceSnapshot | None = None
    health: HealthState | None = None
    gate: GateResult | None = None
    # Provider-independent messages fitted to this model's context window.
    messages: Sequence[dict[str, str]] | None = None
    outbound_check: Callable[[bytes], GateResult] | None = None
    tier: str | None = None  # "local" | "cheap" | "strong"
    input_tokens: int | None = None
    budget_remaining_usd: float | None = None
    meta: dict = field(default_factory=dict)  # e.g. consent preview, never raw text of secrets


@dataclass(frozen=True)
class PipelineRequest:
    prompt: str
    messages: Sequence[dict[str, str]]
    features: Features
    reserved_output: int = 512
    budget_remaining_usd: float | None = None
    max_retries: int = 1
    pre_removed: tuple[dict, ...] = ()


@dataclass(frozen=True)
class PipelineEvent:
    type: str
    data: dict


def _status_for(exc: AdapterError) -> str:
    return "timeout" if exc.error_class == "timeout" else "fail"


async def run_pipeline(
    request: PipelineRequest,
    candidates: list[PipelineCandidate],
    *,
    policy: Policy | None = None,
    shadow_policy: Policy | None = None,
    on_record: Callable[[str, dict], None] | None = None,
) -> AsyncIterator[PipelineEvent]:
    policy = policy or FixedRules()
    started = time.perf_counter()

    def record(kind: str, data: dict) -> None:
        if on_record:
            on_record(kind, data)

    by_slug = {candidate.model.slug: candidate for candidate in candidates}
    tiers = {
        candidate.model.slug: candidate.tier
        or ("local" if candidate.model.kind == "local" else "strong")
        for candidate in candidates
    }
    features = replace(request.features, tiers={**request.features.tiers, **tiers})

    def tokens_for(candidate: PipelineCandidate) -> int:
        return (
            candidate.input_tokens
            if candidate.input_tokens is not None
            else request.features.input_tokens
        )

    def reserved_for(candidate: PipelineCandidate) -> int:
        return min(request.reserved_output, candidate.model.max_output)

    def estimate(candidate: PipelineCandidate, latency: bool = True):
        return estimate_candidate(
            candidate.model,
            candidate.price,
            input_tokens=tokens_for(candidate),
            reserved_output=reserved_for(candidate),
            latency_ms=candidate.health.p50_ms if (latency and candidate.health) else None,
        )

    prices = {slug: candidate.price for slug, candidate in by_slug.items()}
    health = {slug: candidate.health for slug, candidate in by_slug.items()}
    gates = {slug: candidate.gate for slug, candidate in by_slug.items()}
    budgets = {slug: candidate.budget_remaining_usd for slug, candidate in by_slug.items()}

    def eligibility(subset: list[PipelineCandidate]):
        return eligible_candidates(
            [estimate(candidate) for candidate in subset],
            prices=prices,
            health=health,
            gates=gates,
            budget_remaining_usd=request.budget_remaining_usd,
            budgets=budgets,
        )

    eligible, removed = eligibility(candidates)
    removed_list = [dict(item) for item in request.pre_removed] + [
        {"model": item.model, "reason": item.reason} for item in removed
    ]
    if not eligible:
        detail = {
            "removed": removed_list,
            "consent_needed": [
                {"model": slug, "payload_hash": c.gate.payload_hash, **c.meta}
                for slug, c in by_slug.items()
                if c.gate is not None and c.gate.reason == "consent_required"
            ],
            "suggestion": (
                "Change privacy mode, add a provider key, shorten the document, "
                "grant scoped consent, or retry later."
            ),
            "routing_latency_ms": (time.perf_counter() - started) * 1000,
        }
        record("abstain", detail)  # record first: consumers persist on the yielded event
        yield PipelineEvent("abstain", detail)
        return

    eligible_slugs = [item.estimate.model.slug for item in eligible]
    decision: Decision = policy.select(features, eligible_slugs)
    if decision.action not in eligible_slugs:  # defensive: policies must never escape A
        decision = FixedRules().select(features, eligible_slugs)
        decision = replace(decision, rule_id="policy_invalid_fallback")
    shadow = None
    if shadow_policy is not None:
        try:
            counterfactual = shadow_policy.select(features, eligible_slugs)
            if counterfactual.action in eligible_slugs:
                shadow = {
                    "policy": shadow_policy.name,
                    "version": shadow_policy.version,
                    "action": counterfactual.action,
                    "probability": counterfactual.probability,
                    "rule_id": counterfactual.rule_id,
                }
        except Exception:
            shadow = None
    chosen = by_slug[decision.action]
    chosen_estimate = next(
        item.estimate for item in eligible if item.estimate.model.slug == decision.action
    )
    ordered = [decision.action] + [slug for slug in eligible_slugs if slug != decision.action]
    routing_ms = (time.perf_counter() - started) * 1000
    route = {
        "model": decision.action,
        "reason": decision.explanation,
        "rule_id": decision.rule_id,
        "probability": decision.probability,
        "distribution": decision.distribution,
        "policy": policy.name,
        "policy_version": policy.version,
        "estimated_input_tokens": chosen_estimate.input_tokens,
        "estimated_output_tokens": chosen_estimate.reserved_output,
        "estimated_cost_usd": chosen_estimate.cost_usd,
        "estimated_latency_ms": chosen_estimate.latency_ms,
        "routing_latency_ms": routing_ms,
        "routing_target_ms": ROUTING_TARGET_MS,
        "eligible": eligible_slugs,
        "removed": removed_list,
        "shadow": shadow,
        "tier": tiers[chosen.model.slug],
    }
    record("route", route)  # record first: consumers persist on the yielded event
    yield PipelineEvent("route", route)

    failures: list[dict] = []
    attempts = 0
    for slug in ordered:
        if attempts > request.max_retries:
            break
        candidate = by_slug[slug]
        if slug != decision.action:
            # Every retry/fallback repeats eligibility (invariant 5).
            refreshed, _ = eligibility([candidate])
            if not refreshed:
                continue
        messages = candidate.messages if candidate.messages is not None else request.messages
        attempt_started = time.perf_counter()
        first_token_ms: float | None = None
        emitted = False
        status = "fail"
        error_class: str | None = None
        usage = None
        try:
            async for chunk in send(
                candidate.adapter,
                messages,
                GenerationParams(
                    max_output_tokens=reserved_for(candidate),
                    context_limit=candidate.model.context_limit,
                ),
                privacy_gate=(
                    candidate.model.kind == "local"
                    or bool(candidate.gate and candidate.gate.allowed)
                ),
                outbound_check=candidate.outbound_check,
            ):
                if chunk.text:
                    if first_token_ms is None:
                        first_token_ms = (time.perf_counter() - attempt_started) * 1000
                    emitted = True
                    yield PipelineEvent("token", {"text": chunk.text, "model": slug})
                if chunk.done:
                    usage = chunk.usage
            status = "ok" if emitted else "empty"
        except EgressBlocked as exc:
            status, error_class = "blocked", exc.reason
        except AdapterError as exc:
            status, error_class = _status_for(exc), exc.error_class
        except Exception:  # never leak provider/internal details to the client
            status, error_class = "fail", "unexpected_error"

        latency_ms = (time.perf_counter() - attempt_started) * 1000
        attempt = {
            "attempt_no": len(failures) + 1,
            "model": slug,
            "status": status,
            "error_class": error_class,
            "input_tokens": usage.input_tokens if usage else None,
            "output_tokens": usage.output_tokens if usage else None,
            "cost_usd": usage.cost_usd if usage else None,
            "latency_ms": latency_ms,
            "ttft_ms": first_token_ms,
        }
        record("attempt", attempt)
        if status == "ok":
            done = {
                "model": slug,
                "status": "succeeded",
                "input_tokens": attempt["input_tokens"],
                "output_tokens": attempt["output_tokens"],
                "measured_cost_usd": attempt["cost_usd"],
                "latency_ms": (time.perf_counter() - started) * 1000,
                "generation_latency_ms": latency_ms,
                "ttft_ms": first_token_ms,
                "failures": failures,
            }
            record("done", done)  # record first: consumers persist on the yielded event
            yield PipelineEvent("done", done)
            return
        failures.append({k: attempt[k] for k in ("model", "status", "error_class")})
        if status == "blocked":
            continue  # a privacy block is not a model failure and does not use a retry
        attempts += 1
        if emitted:
            break  # no model switch during a generation (invariant 5)

    detail = {
        "status": "failed",
        "failures": failures,
        "suggestion": "Retry later or change the selected model/provider.",
    }
    record("error", detail)  # record first: consumers persist on the yielded event
    yield PipelineEvent("error", detail)
