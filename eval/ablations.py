"""Ablations and error analysis (Phase 10). Same shared evidence/constraints as the main runs."""

from __future__ import annotations

import argparse
from dataclasses import replace

import numpy as np
from app.routing.bandit import EpsilonGreedyRidge, Scaler
from app.routing.reward import RewardConfig, reward

from eval.common import DATASETS, read_jsonl
from eval.replay import replay
from eval.runner import Handoff, prepare_item, setup

FEATURE_GROUPS = {
    "no_retrieval_stats": ("retrieval_top_score", "retrieval_margin", "evidence_tokens"),
    "no_size_features": ("input_tokens", "estimated_output_tokens", "doc_pages", "history_turns"),
    "no_model_stats": ("stats",),
}


def _mean_reward(steps: list[dict]) -> float | None:
    values = [s["reward"] for s in steps if not s["abstained"] and s["reward"] is not None]
    return round(float(np.mean(values)), 4) if values else None


def _fresh(seed: int, **kw) -> Handoff:
    params = dict(version="abl", seed=seed, cold_start_min=0)
    params.update(kw)
    return Handoff(EpsilonGreedyRidge({}, {}, Scaler(), **params))


def reward_weight_sensitivity(oracle_rows: list[dict]) -> dict:
    """Does the best model per task change when reward weights change? (recomputed offline)"""
    base = RewardConfig.load()
    variants = {
        "default": base,
        "quality_heavy": replace(base, w_quality=0.8, w_cost=0.1, w_latency=0.1),
        "cost_heavy": replace(base, w_quality=0.3, w_cost=0.6, w_latency=0.1),
        "latency_heavy": replace(base, w_quality=0.3, w_cost=0.1, w_latency=0.6),
    }
    out = {}
    for name, cfg in variants.items():
        by_task: dict[str, dict[str, list[float]]] = {}
        for r in oracle_rows:
            if r["status"] != "ok" or r["quality"] is None:
                value = -1.0
            else:
                value = reward(r["quality"], r["cost"], r["latency"], cfg)
            by_task.setdefault(r["task"], {}).setdefault(r["model"], []).append(value)
        out[name] = {
            task: max(models, key=lambda m: float(np.mean(models[m])))
            for task, models in by_task.items()
        }
    return out


def run_ablations(dataset_name: str, executor_kind: str = "sim", seed: int = 0) -> dict:
    ds, items, profiles, executor = setup(dataset_name, executor_kind, seed)
    cfg = RewardConfig.load()
    stream = [
        prepare_item(i, ds, profiles)
        for i in sorted(items, key=lambda i: i.item_id)
        if i.split == "test"
    ]
    oracle = read_jsonl(DATASETS / dataset_name / "results" / "oracle.jsonl")
    result: dict = {"reward_weights_best_model_by_task": reward_weight_sensitivity(oracle)}

    steps, _ = replay(stream, _fresh(seed), executor, profiles, cfg, update_every=10)
    full = _mean_reward(steps)
    result["feature_ablations"] = {"full": full}
    for name, fields in FEATURE_GROUPS.items():

        def transform(features, _fields=fields):
            # neutralise the feature group: int -> 0, float -> 0.0, dict -> {}
            return replace(features, **{f: type(getattr(features, f))() for f in _fields})

        steps, _ = replay(
            stream,
            _fresh(seed),
            executor,
            profiles,
            cfg,
            update_every=10,
            feature_transform=transform,
        )
        result["feature_ablations"][name] = _mean_reward(steps)

    result["epsilon_schedule"] = {}
    for label, (e0, e1) in {
        "0.00-0.00": (0.0, 0.0),
        "0.10-0.02": (0.10, 0.02),
        "0.30-0.10": (0.30, 0.10),
    }.items():
        steps, _ = replay(
            stream,
            _fresh(seed, epsilon_initial=e0, epsilon_final=e1, epsilon_decay=max(1, len(stream))),
            executor,
            profiles,
            cfg,
            update_every=10,
        )
        result["epsilon_schedule"][label] = _mean_reward(steps)
    return result


def error_analysis(rows: list[dict]) -> dict:
    """Failure categories, abstention reasons and where each policy sends traffic."""
    failures: dict[str, int] = {}
    abstain: dict[str, int] = {}
    routes: dict[str, dict[str, int]] = {}
    for r in rows:
        if r["abstained"]:
            for item in r.get("removed", []):
                abstain[item["reason"]] = abstain.get(item["reason"], 0) + 1
        else:
            routes.setdefault(r["policy"], {}).setdefault(r["model"], 0)
            routes[r["policy"]][r["model"]] += 1
            if r["status"] != "ok":
                key = f"{r['model']}:{r['status']}"
                failures[key] = failures.get(key, 0) + 1
    return {"failures": failures, "abstention_reasons": abstain, "routes_by_policy": routes}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", default="synthetic-smoke")
    parser.add_argument("--executor", choices=["sim", "live"], default="sim")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    print(run_ablations(args.dataset, args.executor, args.seed))


if __name__ == "__main__":
    main()
