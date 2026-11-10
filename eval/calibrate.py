"""Calibration: ~50 scored non-sensitive TRAIN examples per model -> initial regressors."""

from __future__ import annotations

import argparse
import json

from app.routing.bandit import EpsilonGreedyRidge, Outcome, Scaler
from app.routing.config import routing_config

from eval.common import ARTIFACTS, DATASETS, read_jsonl, stable_hash


def calibrate(dataset_name: str, per_model: int = 50, seed: int = 0) -> dict:
    dataset = DATASETS / dataset_name
    rows = [
        r
        for r in read_jsonl(dataset / "results" / "oracle.jsonl")
        if r["split"] == "train" and r["label"] == "public" and r["reward"] is not None
    ]
    cfg = routing_config().get("bandit", {})
    batch: list[Outcome] = []
    for slug in sorted({r["model"] for r in rows}):
        mine = [r for r in rows if r["model"] == slug][:per_model]
        batch += [Outcome(slug, r["features"], r["reward"]) for r in mine]
    policy = EpsilonGreedyRidge(
        {},
        {},
        Scaler(),
        version="calibration",
        lam=float(cfg.get("ridge_lambda", 1.0)),
        cold_start_min=int(cfg.get("cold_start_min", 50)),
        epsilon_initial=float(cfg.get("initial_epsilon", 0.10)),
        epsilon_final=float(cfg.get("final_epsilon", 0.02)),
        epsilon_decay=int(cfg.get("decay_decisions", 1000)),
        seed=seed,
    ).update(batch)
    params = policy.to_params()
    digest = stable_hash(json.dumps(params, sort_keys=True))[:12]
    artifact = {
        "version": f"calibration-{digest}",
        "dataset": dataset_name,
        "per_model_n": policy.counts,
        "ready": policy.ready,
        "params": params,
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / f"{dataset_name}-calibration.json").write_text(
        json.dumps(artifact, indent=1), encoding="utf-8"
    )
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", default="synthetic-smoke")
    parser.add_argument("--per-model", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    artifact = calibrate(args.dataset, args.per_model, args.seed)
    print(
        f"calibration {artifact['version']}: n={artifact['per_model_n']} ready={artifact['ready']}"
    )


if __name__ == "__main__":
    main()
