"""Reward math (docs/05). Pure functions; no I/O."""

from dataclasses import dataclass

from app.routing.config import reward_config

FAILURE_REWARD = -1.0


@dataclass(frozen=True)
class RewardConfig:
    w_human: float = 0.7
    w_auto: float = 0.3
    w_quality: float = 0.5
    w_cost: float = 0.3
    w_latency: float = 0.2
    c_ref_usd: float = 0.01
    l_ref_ms: float = 10000.0
    frozen: bool = False

    @classmethod
    def load(cls) -> "RewardConfig":
        raw = reward_config()
        weights = raw.get("weights", {})
        return cls(
            w_human=float(weights.get("human", 0.7)),
            w_auto=float(weights.get("automatic", 0.3)),
            w_quality=float(weights.get("quality", 0.5)),
            w_cost=float(weights.get("cost", 0.3)),
            w_latency=float(weights.get("latency", 0.2)),
            c_ref_usd=float(raw.get("c_ref_usd") or 0.01),
            l_ref_ms=float(raw.get("l_ref_ms") or 10000.0),
            frozen=bool(raw.get("frozen", False)),
        )


def human_score(correctness: float, relevance: float, completeness: float, usefulness: float):
    """H in [0,1] from four 1-5 ratings."""
    values = (correctness, relevance, completeness, usefulness)
    if any(v < 1 or v > 5 for v in values):
        raise ValueError("ratings must be in 1..5")
    return (sum(values) / 4 - 1) / 4


def combine_quality(
    human: float | None, auto: float | None, config: RewardConfig | None = None
) -> tuple[float | None, str | None]:
    """Q = 0.7H + 0.3A if both, the available one otherwise, None when neither (defer)."""
    config = config or RewardConfig()
    if human is not None and auto is not None:
        total = config.w_human + config.w_auto
        return (config.w_human * human + config.w_auto * auto) / total, "both"
    if human is not None:
        return human, "human"
    if auto is not None:
        return auto, "auto"
    return None, None


def reward(
    quality: float,
    cost_usd: float,
    latency_ms: float,
    config: RewardConfig | None = None,
) -> float:
    config = config or RewardConfig()
    cost_term = 1 - min(max(cost_usd, 0.0) / config.c_ref_usd, 1.0)
    latency_term = 1 - min(max(latency_ms, 0.0) / config.l_ref_ms, 1.0)
    return config.w_quality * quality + config.w_cost * cost_term + config.w_latency * latency_term
