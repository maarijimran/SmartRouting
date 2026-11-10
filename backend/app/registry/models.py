from dataclasses import dataclass
from typing import Literal

ModelKind = Literal["local", "cloud"]


@dataclass(frozen=True)
class ModelSpec:
    slug: str
    kind: ModelKind
    provider: str
    context_limit: int
    max_output: int
    enabled: bool = True
    min_ram_gb: float = 0
    min_vram_gb: float = 0


@dataclass(frozen=True)
class PriceSnapshot:
    input_per_mtok: float
    output_per_mtok: float
    captured_at: str
    source: str


@dataclass(frozen=True)
class HealthState:
    ok: bool
    p50_ms: float | None = None
    error_rate: float = 0.0
