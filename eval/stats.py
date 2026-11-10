"""Statistics: document-clustered bootstrap CIs, paired differences, off-policy estimators."""

from __future__ import annotations

import numpy as np


def cluster_bootstrap(
    clusters: dict[str, list[float]],
    stat=np.mean,
    n_boot: int = 2000,
    seed: int = 0,
    alpha: float = 0.05,
) -> tuple[float, float, float]:
    """(point, lo, hi): resample whole documents (clusters) with replacement."""
    keys = sorted(clusters)
    if not keys:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    point = float(stat(np.concatenate([np.asarray(clusters[k], float) for k in keys])))
    draws = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, len(keys), len(keys))
        draws[b] = stat(np.concatenate([np.asarray(clusters[keys[i]], float) for i in pick]))
    return point, float(np.quantile(draws, alpha / 2)), float(np.quantile(draws, 1 - alpha / 2))


def _by_doc(pairs: list[tuple[str, float]]) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for doc, value in pairs:
        out.setdefault(doc, []).append(value)
    return out


def paired_difference_ci(
    a: dict[str, float], b: dict[str, float], doc_of: dict[str, str], **kw
) -> tuple[float, float, float]:
    """Paired (a - b) on shared items, resampled by document."""
    shared = sorted(set(a) & set(b))
    return cluster_bootstrap(_by_doc([(doc_of[i], a[i] - b[i]) for i in shared]), **kw)


def cost_reduction_ci(
    cost_a: dict[str, float],
    cost_b: dict[str, float],
    doc_of: dict[str, str],
    n_boot: int = 2000,
    seed: int = 0,
) -> tuple[float, float, float]:
    """Relative reduction 1 - sum(a)/sum(b), bootstrapped over documents (a vs reference b)."""
    shared = sorted(set(cost_a) & set(cost_b))
    docs: dict[str, list[int]] = {}
    for idx, item in enumerate(shared):
        docs.setdefault(doc_of[item], []).append(idx)
    keys = sorted(docs)
    if not keys:
        return float("nan"), float("nan"), float("nan")
    xa = np.array([cost_a[i] for i in shared])
    xb = np.array([cost_b[i] for i in shared])

    def red(idx: np.ndarray) -> float:
        denom = xb[idx].sum()
        return float(1 - xa[idx].sum() / denom) if denom > 0 else float("nan")

    point = red(np.arange(len(shared)))
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(keys), len(keys))
        idx = np.concatenate([docs[keys[i]] for i in pick])
        draws.append(red(idx))
    draws = np.array([d for d in draws if not np.isnan(d)])
    return point, float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def ips_value(logs: list[dict], target_prob, self_normalise: bool = True) -> float:
    """Inverse-propensity estimate of a target policy's value from logged (x, a, p, r).

    ``target_prob(log, action)`` returns pi(action | x). Logged propensities must be > 0.
    """
    weights = np.array([target_prob(lg, lg["action"]) / lg["prob"] for lg in logs])
    rewards = np.array([lg["reward"] for lg in logs])
    if self_normalise:
        return float((weights * rewards).sum() / weights.sum()) if weights.sum() > 0 else 0.0
    return float((weights * rewards).mean())


def doubly_robust_value(logs: list[dict], target_dist, reward_model) -> float:
    """DR estimate. ``target_dist(log)`` -> {action: pi}; ``reward_model(log, action)`` -> r_hat."""
    values = []
    for lg in logs:
        dist = target_dist(lg)
        direct = sum(p * reward_model(lg, a) for a, p in dist.items())
        correction = (
            dist.get(lg["action"], 0.0)
            / lg["prob"]
            * (lg["reward"] - reward_model(lg, lg["action"]))
        )
        values.append(direct + correction)
    return float(np.mean(values))
