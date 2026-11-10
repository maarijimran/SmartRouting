from dataclasses import dataclass
from time import perf_counter

from sqlalchemy.orm import Session

from app.db.models import Model, ModelHealth


@dataclass(frozen=True)
class HealthProbeResult:
    ok: bool
    latency_ms: float
    error_rate: float = 0.0


def record_health(db: Session, model: Model, result: HealthProbeResult) -> ModelHealth:
    health = ModelHealth(
        model_id=model.id,
        ok=result.ok,
        p50_ms=result.latency_ms,
        err_rate=result.error_rate,
    )
    db.add(health)
    db.commit()
    db.refresh(health)
    return health


def probe(probe_call) -> HealthProbeResult:
    started = perf_counter()
    try:
        ok = bool(probe_call())
    except Exception:
        ok = False
    return HealthProbeResult(ok, (perf_counter() - started) * 1000)
