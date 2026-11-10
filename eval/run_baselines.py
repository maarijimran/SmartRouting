"""Run every policy over a split with shared evidence, constraints and cache.

Policies: local_only, strong_cloud_only, fixed_rules, frozen_supervised, adaptive_bandit.
The adaptive policy is evaluated predict-then-update over the stream (cold start -> rules).
"""

from __future__ import annotations

import argparse
import json

import numpy as np
from app.routing.bandit import EpsilonGreedyRidge, Scaler
from app.routing.frozen import FrozenRouter
from app.routing.reward import RewardConfig
from app.routing.rules import FixedRules, LocalOnly, StrongCloudOnly

from eval.common import ARTIFACTS, write_jsonl
from eval.replay import replay
from eval.runner import Handoff, prepare_item, run_item, setup

POLICY_NAMES = (
    "local_only",
    "strong_cloud_only",
    "fixed_rules",
    "frozen_supervised",
    "adaptive_bandit",
)


def _artifact(dataset_name: str, kind: str):
    path = ARTIFACTS / f"{dataset_name}-{kind}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def build_policies(dataset_name: str, seed: int, *, adaptive_cold: bool = False) -> dict:
    policies: dict = {
        "local_only": LocalOnly(),
        "strong_cloud_only": StrongCloudOnly(),
        "fixed_rules": FixedRules(),
    }
    frozen = _artifact(dataset_name, "frozen")
    if frozen:
        policies["frozen_supervised"] = FrozenRouter.from_params(
            frozen["params"], version=frozen["version"]
        )
    calibration = _artifact(dataset_name, "calibration")
    if calibration and not adaptive_cold:
        learned = EpsilonGreedyRidge.from_params(
            calibration["params"], version=calibration["version"]
        )
    else:
        learned = EpsilonGreedyRidge({}, {}, Scaler(), version="cold")
    learned.seed = seed
    learned._rng = np.random.default_rng(seed)
    policies["adaptive_bandit"] = Handoff(learned)
    return policies


def run_baselines(
    dataset_name: str,
    executor_kind: str = "sim",
    seeds: tuple[int, ...] = (0, 1, 2),
    split: str = "test",
    limit: int | None = None,
    adaptive_cold: bool = False,
) -> list[dict]:
    rows: list[dict] = []
    cfg = RewardConfig.load()
    for seed in seeds:
        dataset, items, profiles, executor = setup(dataset_name, executor_kind, seed)
        chosen = [i for i in items if i.split == split]
        chosen = sorted(chosen, key=lambda i: i.item_id)[:limit] if limit else chosen
        prepared = [prepare_item(i, dataset, profiles) for i in chosen]
        for name, policy in build_policies(dataset_name, seed, adaptive_cold=adaptive_cold).items():
            if name == "adaptive_bandit":
                records, _ = replay(prepared, policy, executor, profiles, cfg)
            else:
                records = [run_item(p, policy, executor, profiles, cfg) for p in prepared]
            for r in records:
                rows.append({**r, "policy": name, "seed": seed})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", default="synthetic-smoke")
    parser.add_argument("--executor", choices=["sim", "live"], default="sim")
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--split", default="test")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--cold", action="store_true", help="start the adaptive policy uncalibrated"
    )
    args = parser.parse_args()
    rows = run_baselines(
        args.dataset, args.executor, tuple(args.seeds), args.split, args.limit, args.cold
    )
    from eval.common import DATASETS

    write_jsonl(DATASETS / args.dataset / "results" / f"baselines-{args.split}.jsonl", rows)
    by_policy: dict[str, int] = {}
    for r in rows:
        by_policy[r["policy"]] = by_policy.get(r["policy"], 0) + 1
    print(f"baselines: {len(rows)} records {by_policy}")


if __name__ == "__main__":
    main()
