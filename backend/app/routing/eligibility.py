from dataclasses import dataclass

from app.privacy.gate import GateResult
from app.registry.eligibility import eligible_for_dispatch
from app.registry.models import HealthState, PriceSnapshot
from app.routing.features import CandidateEstimate


@dataclass(frozen=True)
class RemovedModel:
    model: str
    reason: str


@dataclass(frozen=True)
class EligibleModel:
    estimate: CandidateEstimate
    gate: GateResult | None


def eligible_candidates(
    estimates: list[CandidateEstimate],
    *,
    prices: dict[str, PriceSnapshot | None],
    health: dict[str, HealthState | None],
    gates: dict[str, GateResult | None],
    budget_remaining_usd: float | None = None,
    budgets: dict[str, float | None] | None = None,
) -> tuple[list[EligibleModel], list[RemovedModel]]:
    """Return (eligible set A, removed models with reasons).

    Policies only ever see A, so no learned or rule-based policy can select an
    ineligible model.
    """
    allowed: list[EligibleModel] = []
    removed: list[RemovedModel] = []
    for estimate in estimates:
        model = estimate.model
        result = eligible_for_dispatch(
            model,
            prices.get(model.slug),
            health.get(model.slug),
            input_tokens=estimate.input_tokens,
            reserved_output=estimate.reserved_output,
        )
        if not result.allowed:
            removed.append(RemovedModel(model.slug, result.reason or "ineligible"))
            continue
        if model.kind == "cloud":
            gate = gates.get(model.slug)
            if gate is None or not gate.allowed:
                removed.append(RemovedModel(model.slug, gate.reason if gate else "privacy_blocked"))
                continue
            budget = (budgets or {}).get(model.slug, budget_remaining_usd)
            if budget is not None and (estimate.cost_usd is None or estimate.cost_usd > budget):
                removed.append(RemovedModel(model.slug, "over_budget"))
                continue
        allowed.append(EligibleModel(estimate, gates.get(model.slug)))
    return allowed, removed
