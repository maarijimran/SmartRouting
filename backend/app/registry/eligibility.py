from dataclasses import dataclass

from app.registry.health import is_healthy
from app.registry.models import HealthState, ModelSpec, PriceSnapshot


@dataclass(frozen=True)
class Eligibility:
    allowed: bool
    reason: str | None = None


def eligible_for_dispatch(
    model: ModelSpec,
    price: PriceSnapshot | None,
    health: HealthState | None,
    *,
    input_tokens: int,
    reserved_output: int,
) -> Eligibility:
    if not model.enabled:
        return Eligibility(False, "model_disabled")
    if model.kind == "cloud" and price is None:
        return Eligibility(False, "price_unknown")
    if not is_healthy(health):
        return Eligibility(False, "host_unhealthy")
    if input_tokens + reserved_output > model.context_limit:
        return Eligibility(False, "context_infeasible")
    return Eligibility(True)
