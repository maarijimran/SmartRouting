"""Predict-then-update replay engine.

The learner sees only the outcome of the action it selected, in stream order, and is
updated in batches. Deterministic for a given seed. Supports a controlled latency shift
(``shift={"at": N, "model": slug, "latency_factor": F}``) and a task-mix shift (the stream
order itself is reordered by the caller).
"""

from __future__ import annotations

from collections.abc import Callable

from app.routing.bandit import Outcome
from app.routing.reward import RewardConfig

from eval.executor import ModelProfile
from eval.runner import PreparedItem, run_item


def _ewma(old: float, new: float, alpha: float = 0.3) -> float:
    return new if old == 0.0 else (1 - alpha) * old + alpha * new


def replay(
    stream: list[PreparedItem],
    policy,
    executor,
    profiles: dict[str, ModelProfile],
    cfg: RewardConfig,
    *,
    update_every: int = 50,
    shift: dict | None = None,
    feature_transform: Callable | None = None,
    oracle_best: dict[str, float] | None = None,
) -> tuple[list[dict], object]:
    """Run the stream; returns (step records, final policy). Use a fresh policy per replay."""
    from eval.runner import with_stats

    buffer: list[Outcome] = []
    stats: dict[str, tuple[float, float]] = {}
    steps: list[dict] = []
    for t, prep in enumerate(stream):
        if shift and t == shift["at"]:
            executor.latency_factor[shift["model"]] = shift["latency_factor"]
        features = with_stats(prep.features, stats)
        if feature_transform is not None:
            features = feature_transform(features)
        record = run_item(prep, policy, executor, profiles, cfg, features)
        record["t"] = t
        if not record["abstained"]:
            slug = record["model"]
            lat, fail = stats.get(slug, (0.0, 0.0))
            stats[slug] = (
                _ewma(lat, record["latency"] or 0.0),
                _ewma(fail, 1.0 if record["status"] != "ok" else 0.0),
            )
            buffer.append(Outcome(slug, features.to_log(), record["reward"]))
            if oracle_best is not None and prep.item.item_id in oracle_best:
                record["regret"] = oracle_best[prep.item.item_id] - record["reward"]
            if hasattr(policy, "update") and len(buffer) >= update_every:
                policy = policy.update(buffer)
                buffer = []
        steps.append(record)
    return steps, policy
