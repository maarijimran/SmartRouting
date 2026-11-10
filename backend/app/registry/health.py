from app.registry.models import HealthState, ModelSpec


def local_hardware_available(model: ModelSpec, ram_gb: float, vram_gb: float) -> bool:
    return ram_gb >= model.min_ram_gb and vram_gb >= model.min_vram_gb


def is_healthy(state: HealthState | None) -> bool:
    return state is not None and state.ok and state.error_rate < 1.0
