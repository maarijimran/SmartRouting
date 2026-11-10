"""One command: build -> oracle -> calibrate -> frozen -> static -> stream -> privacy -> stats.

Every artefact is written under eval/reports/<run_id>/ with seeds, git SHA, config hash,
model IDs and price snapshot. Simulated runs are labelled and must not be reported as
experimental results.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from app.routing.bandit import EpsilonGreedyRidge, Scaler
from app.routing.reward import RewardConfig

from eval import build_dataset
from eval.ablations import error_analysis, run_ablations
from eval.calibrate import calibrate
from eval.common import CACHE, DATASETS, REPORTS, config_hash, git_sha, write_jsonl
from eval.executor import ModelProfile
from eval.oracle import run_oracle
from eval.privacy_eval import privacy_eval
from eval.replay import replay
from eval.report import summarize, to_markdown
from eval.run_baselines import run_baselines
from eval.runner import Handoff, prepare_item, setup
from eval.splits import write_splits
from eval.train_frozen import train_frozen


def budget_sheet(profiles: dict[str, ModelProfile]) -> dict:
    import yaml

    from eval.common import ROOT

    cfg = yaml.safe_load((ROOT / "configs" / "budget.yaml").read_text(encoding="utf-8"))
    spent = 0.0
    for ledger in CACHE.glob("*/ledger.csv"):
        spent += sum(float(line.split(",")[1]) for line in ledger.read_text().splitlines() if line)
    return {
        "projected_caps_usd": cfg,
        "spent_live_usd": round(spent, 6),
        "note": "simulated runs spend USD 0; only live cloud calls enter the ledger",
    }


def stream_experiment(dataset: str, executor_kind: str, seed: int) -> dict:
    """Controlled latency shift on the strong model; predict first, update after."""
    ds, items, profiles, executor = setup(dataset, executor_kind, seed)
    cfg = RewardConfig.load()
    test = sorted((i for i in items if i.split == "test"), key=lambda i: i.item_id)
    prepared = [prepare_item(i, ds, profiles) for i in test]
    if len(prepared) < 4:
        return {"skipped": "too few test items"}
    shift = {"at": len(prepared) // 2, "model": "cloud-strong-eval", "latency_factor": 6.0}
    out = {}
    for name, policy in {
        "fixed_rules": Handoff(EpsilonGreedyRidge({}, {}, Scaler(), version="cold")),
        "adaptive_bandit": Handoff(
            EpsilonGreedyRidge({}, {}, Scaler(), version="cold", seed=seed, cold_start_min=0)
        ),
    }.items():
        executor.latency_factor.clear()
        steps, _ = replay(prepared, policy, executor, profiles, cfg, update_every=10, shift=shift)
        answered = [s for s in steps if not s["abstained"]]
        half = shift["at"]
        before = [s["reward"] for s in answered if s["t"] < half]
        after = [s["reward"] for s in answered if s["t"] >= half]
        out[name] = {
            "mean_reward_before_shift": round(sum(before) / len(before), 4) if before else None,
            "mean_reward_after_shift": round(sum(after) / len(after), 4) if after else None,
        }
    executor.latency_factor.clear()
    return {"shift": shift, **out}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", default="synthetic-smoke")
    parser.add_argument("--executor", choices=["sim", "live"], default="sim")
    parser.add_argument("--scale", type=float, default=0.3)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()

    ds = DATASETS / args.dataset
    if args.rebuild or not (ds / "items.jsonl").exists():
        import sys

        sys.argv = ["build", "--name", args.dataset, "--scale", str(args.scale), "--seed", "0"]
        build_dataset.main()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = REPORTS / run_id
    out.mkdir(parents=True, exist_ok=True)

    run_oracle(args.dataset, args.executor, args.seeds[0])
    calibrate(args.dataset, seed=args.seeds[0])
    train_frozen(args.dataset)
    rows = run_baselines(args.dataset, args.executor, tuple(args.seeds), "test")
    write_jsonl(out / "static_results.jsonl", rows)
    summary = summarize(rows)
    provenance = (
        "SIMULATED (pipeline check only, not a result)" if args.executor == "sim" else "live"
    )
    _, _, profiles, _ = setup(args.dataset, args.executor, args.seeds[0])
    report = {
        "run_id": run_id,
        "provenance": provenance,
        "dataset": args.dataset,
        "seeds": args.seeds,
        "git_sha": git_sha(),
        "config_hash": config_hash(),
        "reward_config": RewardConfig.load().__dict__,
        "models": {
            slug: {
                "provider_model": p.provider_model,
                "price_in": p.price_in,
                "price_out": p.price_out,
            }
            for slug, p in profiles.items()
        },
        "splits_sha256": json.loads((ds / "splits.json").read_text())["sha256"],
        "static": summary,
        "stream": stream_experiment(args.dataset, args.executor, args.seeds[0]),
        "privacy": privacy_eval(args.dataset),
        "ablations": run_ablations(args.dataset, args.executor, args.seeds[0]),
        "error_analysis": error_analysis(rows),
        "budget": budget_sheet(profiles),
    }
    (out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (out / "report.md").write_text(to_markdown(summary, provenance), encoding="utf-8")
    print(to_markdown(summary, provenance))
    print(f"report written to {out}")
    _ = write_splits


if __name__ == "__main__":
    main()
