"""Train the frozen supervised router once on the TRAIN split (all-model oracle outcomes)."""

from __future__ import annotations

import argparse
import json

from app.routing.bandit import Outcome
from app.routing.frozen import FrozenRouter

from eval.common import ARTIFACTS, DATASETS, read_jsonl, stable_hash


def train_frozen(dataset_name: str) -> dict:
    dataset = DATASETS / dataset_name
    rows = [
        r
        for r in read_jsonl(dataset / "results" / "oracle.jsonl")
        if r["split"] == "train" and r["reward"] is not None
    ]
    if not rows:
        raise SystemExit("no train-split oracle outcomes; run `make eval-oracle` first")
    router = FrozenRouter.train(
        [Outcome(r["model"], r["features"], r["reward"]) for r in rows], version="frozen-0"
    )
    params = router.to_params()
    artifact = {
        "version": f"frozen-{stable_hash(json.dumps(params, sort_keys=True))[:12]}",
        "dataset": dataset_name,
        "per_model_n": router.counts,
        "params": params,
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / f"{dataset_name}-frozen.json").write_text(
        json.dumps(artifact, indent=1), encoding="utf-8"
    )
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", default="synthetic-smoke")
    args = parser.parse_args()
    artifact = train_frozen(args.dataset)
    print(f"frozen router {artifact['version']}: n={artifact['per_model_n']}")


if __name__ == "__main__":
    main()
