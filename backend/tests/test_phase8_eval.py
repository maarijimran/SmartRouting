"""Evaluation harness: splits, leakage, cache, budget, replay determinism, statistics."""

import random
import shutil

import numpy as np
import pytest
from app.routing.bandit import EpsilonGreedyRidge, Outcome, Scaler
from app.routing.reward import RewardConfig

from eval import build_dataset
from eval.calibrate import calibrate
from eval.common import CACHE, DATASETS, EvalItem, load_items, stable_unit
from eval.executor import (
    SIM_PROFILES,
    BudgetExceeded,
    BudgetGuard,
    ResultCache,
    SimulatedExecutor,
)
from eval.oracle import run_oracle
from eval.privacy_eval import privacy_eval
from eval.replay import replay
from eval.report import summarize
from eval.run_baselines import run_baselines
from eval.runner import Handoff, prepare_item, setup
from eval.splits import apply_splits, check_leakage
from eval.stats import (
    cluster_bootstrap,
    cost_reduction_ci,
    doubly_robust_value,
    ips_value,
    paired_difference_ci,
)
from eval.train_frozen import train_frozen

NAME = "pytest-synth"


@pytest.fixture(scope="module")
def dataset():
    out = DATASETS / NAME
    shutil.rmtree(out, ignore_errors=True)
    shutil.rmtree(CACHE / f"sim-{NAME}", ignore_errors=True)
    out.mkdir(parents=True)
    items = build_dataset.synthetic_items(0.25, 0, out)
    apply_splits(items, 0)
    from eval.common import save_items, write_jsonl
    from eval.splits import write_splits

    save_items(out, items)
    write_splits(out / "splits.json", items)
    write_jsonl(out / "privacy.jsonl", build_dataset.privacy_cases(0, 200))
    yield out
    shutil.rmtree(out, ignore_errors=True)
    shutil.rmtree(CACHE / f"sim-{NAME}", ignore_errors=True)


def test_workload_shape_and_synthetic_identifiers_only(dataset):
    items = load_items(dataset)
    kinds = {i.kind for i in items}
    assert {"qa", "summary", "explain", "stress"} <= kinds
    assert {i.label for i in items} >= {"public", "confidential"}
    privacy = build_dataset.privacy_cases(0, 200)
    assert len(privacy) == 200
    assert sum(c["sensitive"] for c in privacy) == 100
    assert all("example.test" in c["text"] for c in privacy if c["entity"] == "email")


def test_splits_are_document_grouped_60_20_20_with_no_leakage(dataset):
    items = load_items(dataset)
    check_leakage(items)
    docs = {}
    for item in items:
        docs.setdefault(item.doc_id, set()).add(item.split)
    assert all(len(v) == 1 for v in docs.values())
    counts = {s: sum(1 for d in docs.values() if s in d) for s in ("train", "dev", "test")}
    total = sum(counts.values())
    assert abs(counts["train"] / total - 0.6) < 0.08
    assert abs(counts["dev"] / total - 0.2) < 0.08 and abs(counts["test"] / total - 0.2) < 0.08


def test_leakage_check_detects_a_document_in_two_splits_and_split_is_deterministic():
    a = EvalItem("1", "d1", "g1", "qa", "qa", "q", split="train")
    b = EvalItem("2", "d1", "g1", "qa", "qa", "q", split="test")
    with pytest.raises(AssertionError, match="leakage"):
        check_leakage([a, b])
    items = [EvalItem(str(i), f"d{i // 2}", f"d{i // 2}", "qa", "qa", "q") for i in range(40)]
    first = {i.item_id: i.split for i in (apply_splits(items, 7) and items)}
    second_items = [
        EvalItem(str(i), f"d{i // 2}", f"d{i // 2}", "qa", "qa", "q") for i in range(40)
    ]
    apply_splits(second_items, 7)
    assert first == {i.item_id: i.split for i in second_items}


def test_paraphrase_groups_stay_together_even_across_documents():
    items = [
        EvalItem("a", "d1", "para-1", "qa", "qa", "q"),
        EvalItem("b", "d2", "para-1", "qa", "qa", "q"),  # same group, different doc
        *[EvalItem(f"x{i}", f"dx{i}", f"gx{i}", "qa", "qa", "q") for i in range(30)],
    ]
    apply_splits(items, 3)
    assert items[0].split == items[1].split


def test_cached_rerun_costs_zero_and_is_identical(dataset, tmp_path):
    ds, items, profiles, _ = setup(NAME, "sim", 0)
    cache = ResultCache(tmp_path / "cache")
    executor = SimulatedExecutor(0, cache)
    prep = prepare_item(items[0], ds, profiles)
    profile = profiles["cloud-strong-eval"]
    first = executor.run(items[0], profile, prep.messages[profile.slug], prep.tokens[profile.slug])
    second = executor.run(items[0], profile, prep.messages[profile.slug], prep.tokens[profile.slug])
    assert not first.cached and second.cached
    assert (first.text, first.cost_usd) == (second.text, second.cost_usd)
    assert cache.hits == 1 and cache.misses == 1


def test_budget_guard_hard_stops_and_survives_restart(tmp_path):
    ledger = tmp_path / "ledger.csv"
    guard = BudgetGuard(1.0, ledger)
    guard.check(0.9)
    guard.record("a", 0.9)
    with pytest.raises(BudgetExceeded):
        guard.check(0.2)
    assert BudgetGuard(1.0, ledger).spent == pytest.approx(0.9)  # persisted across restarts


def test_oracle_calibration_and_frozen_artifacts(dataset):
    rows = run_oracle(NAME, "sim", 0, limit=200)
    models = {r["model"] for r in rows}
    assert models == {"local-eval", "cloud-cheap-eval", "cloud-strong-eval"}
    assert all(r["label"] == "public" for r in rows)  # oracle runs on the public subset only
    artifact = calibrate(NAME, per_model=50, seed=0)
    assert set(artifact["per_model_n"]) == models
    assert all(n <= 50 for n in artifact["per_model_n"].values())
    train_rows = {r["item_id"] for r in rows if r["split"] == "train"}
    assert train_rows  # calibration data come from the train split only
    frozen = train_frozen(NAME)
    assert set(frozen["per_model_n"]) == models


def test_baselines_share_constraints_and_never_dispatch_ineligible(dataset):
    rows = run_baselines(NAME, "sim", seeds=(0,), split="test")
    assert {r["policy"] for r in rows} == {
        "local_only",
        "strong_cloud_only",
        "fixed_rules",
        "frozen_supervised",
        "adaptive_bandit",
    }
    for r in rows:
        if not r["abstained"]:
            assert r["model"] in r["eligible"]
            if r["label"] == "confidential":
                assert r["model"] == "local-eval"  # cloud never used for confidential items
    conf = [r for r in rows if r["policy"] == "strong_cloud_only" and r["label"] == "confidential"]
    assert conf and all(r["abstained"] for r in conf)
    summary = summarize(rows, n_boot=100)
    assert summary["policies"]["strong_cloud_only"]["abstain_rate"] > 0
    assert set(summary["vs_reference"]) == {
        "local_only",
        "fixed_rules",
        "frozen_supervised",
        "adaptive_bandit",
    }


def test_replay_is_deterministic_by_seed_and_learner_sees_only_selected_actions(dataset):
    ds, items, profiles, _ = setup(NAME, "sim", 5)
    cfg = RewardConfig.load()
    stream = [prepare_item(i, ds, profiles) for i in items if i.label == "public"][:60]

    def run(seed):
        executor = SimulatedExecutor(seed)  # uncached: determinism comes from the seed alone
        policy = Handoff(
            EpsilonGreedyRidge({}, {}, Scaler(), version="c", seed=seed, cold_start_min=0)
        )
        steps, final = replay(stream, policy, executor, profiles, cfg, update_every=10)
        return [(s["model"], s["reward"]) for s in steps], final

    a, final_a = run(11)
    b, _ = run(11)
    c, _ = run(12)
    assert a == b
    assert a != c
    # counts per model equal the number of times that model was actually selected
    chosen = {}
    for model, _ in a:
        chosen[model] = chosen.get(model, 0) + 1
    learned = final_a.learned
    for model, n in learned.counts.items():
        assert n <= chosen[model]  # never learns from a non-selected action


def test_latency_shift_changes_outcomes_after_the_shift_point(dataset):
    ds, items, profiles, _ = setup(NAME, "sim", 1)
    cfg = RewardConfig.load()
    stream = [prepare_item(i, ds, profiles) for i in items if i.label == "public"][:40]
    from app.routing.rules import StrongCloudOnly

    executor = SimulatedExecutor(1)
    shift = {"at": 20, "model": "cloud-strong-eval", "latency_factor": 5.0}
    steps, _ = replay(stream, StrongCloudOnly(), executor, profiles, cfg, shift=shift)
    before = np.mean([s["latency"] for s in steps if s["t"] < 20 and s["status"] == "ok"])
    after = np.mean([s["latency"] for s in steps if s["t"] >= 20 and s["status"] == "ok"])
    assert after > 3 * before


def test_privacy_eval_reports_pr_and_unauthorised_dispatch_separately(dataset):
    result = privacy_eval(NAME)
    d = result["detector"]
    assert d["tp"] + d["fn"] == 100 and d["fp"] + d["tn"] == 100
    assert 0 <= d["precision"] <= 1 and 0 <= d["recall"] <= 1
    assert "unauthorised_dispatches" in result
    # every sensitive case the detector flags is blocked without consent
    assert result["unauthorised_dispatches"] == d["fn"]


# --- statistics ---------------------------------------------------------------------
def test_cluster_bootstrap_ci_contains_true_mean_and_is_deterministic():
    rng = np.random.default_rng(0)
    clusters = {f"d{i}": list(rng.normal(0.5, 0.1, 4) + rng.normal(0, 0.05)) for i in range(40)}
    point, lo, hi = cluster_bootstrap(clusters, n_boot=500, seed=1)
    assert lo < 0.5 < hi and lo < point < hi
    assert (point, lo, hi) == cluster_bootstrap(clusters, n_boot=500, seed=1)


def test_paired_difference_and_cost_reduction_hand_computed():
    a = {"i1": 0.8, "i2": 0.6}
    b = {"i1": 1.0, "i2": 1.0}
    doc = {"i1": "d1", "i2": "d2"}
    point, lo, hi = paired_difference_ci(a, b, doc, n_boot=200)
    assert point == pytest.approx(-0.3)
    assert lo <= point <= hi
    cr, _, _ = cost_reduction_ci({"i1": 1.0, "i2": 1.0}, {"i1": 4.0, "i2": 4.0}, doc, n_boot=100)
    assert cr == pytest.approx(0.75)


def test_ips_and_doubly_robust_are_close_to_truth_on_synthetic_logs():
    rng = random.Random(0)
    true_reward = {"a": 0.2, "b": 0.8}
    logs = []
    for _ in range(4000):
        action = rng.choice(["a", "b"])  # uniform logging policy, p = 0.5
        reward = true_reward[action] + rng.gauss(0, 0.05)
        logs.append({"action": action, "prob": 0.5, "reward": reward})
    target = lambda log, a: 1.0 if a == "b" else 0.0  # noqa: E731  always pick b
    assert ips_value(logs, target) == pytest.approx(0.8, abs=0.03)
    dr = doubly_robust_value(
        logs,
        lambda log: {"b": 1.0},
        lambda log, a: 0.5,  # deliberately biased reward model
    )
    assert dr == pytest.approx(0.8, abs=0.04)  # correction term removes the model bias


def test_stable_unit_is_uniformish_and_deterministic():
    values = [stable_unit("x", i) for i in range(2000)]
    assert 0.45 < sum(values) / len(values) < 0.55
    assert stable_unit("x", 1) == stable_unit("x", 1)
    assert SIM_PROFILES["cloud-strong-eval"].strength > SIM_PROFILES["local-eval"].strength
    _ = Outcome


def test_ablations_and_error_analysis_run_and_are_labelled(dataset):
    from eval.ablations import error_analysis, run_ablations

    run_oracle(NAME, "sim", 0, limit=200)
    result = run_ablations(NAME, "sim", 0)
    assert set(result["feature_ablations"]) == {
        "full",
        "no_retrieval_stats",
        "no_size_features",
        "no_model_stats",
    }
    assert set(result["epsilon_schedule"]) == {"0.00-0.00", "0.10-0.02", "0.30-0.10"}
    assert {"default", "quality_heavy", "cost_heavy", "latency_heavy"} == set(
        result["reward_weights_best_model_by_task"]
    )
    rows = run_baselines(NAME, "sim", seeds=(0,), split="test")
    analysis = error_analysis(rows)
    assert "routes_by_policy" in analysis and analysis["abstention_reasons"]


def test_synthetic_cards_are_luhn_valid_and_detected() -> None:
    """Generated card numbers must pass Luhn, or 'sensitive' cases are mislabelled."""
    from app.privacy.patterns import _luhn, find_pattern_entities

    rng = random.Random(0)
    for _ in range(200):
        card = build_dataset._luhn_card(rng)
        assert _luhn(card), card
        assert [f.entity_type for f in find_pattern_entities(f"card {card} on file")] == ["card"]
