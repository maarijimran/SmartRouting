"""Empirical oracle: run ALL models on a public subset (learner never sees these during replay)."""

from __future__ import annotations

import argparse

from app.routing.reward import RewardConfig

from eval.common import write_jsonl
from eval.runner import oracle_record, prepare_item, setup


def run_oracle(dataset_name: str, executor_kind: str, seed: int, limit: int = 120) -> list[dict]:
    dataset, items, profiles, executor = setup(dataset_name, executor_kind, seed)
    cfg = RewardConfig.load()
    public = [i for i in items if i.label == "public"][:limit]
    rows = []
    for item in public:
        prep = prepare_item(item, dataset, profiles)
        for slug, profile in profiles.items():
            rows.append(oracle_record(prep, slug, executor, profile, cfg))
    write_jsonl(dataset / "results" / "oracle.jsonl", rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", default="synthetic-smoke")
    parser.add_argument("--executor", choices=["sim", "live"], default="sim")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--limit", type=int, default=120)
    args = parser.parse_args()
    rows = run_oracle(args.dataset, args.executor, args.seed, args.limit)
    print(f"oracle: {len(rows)} outcomes ({len(rows) // 3} items x 3 models)")


if __name__ == "__main__":
    main()
