# 06 — Training (what is and isn't "trained") and the evaluation protocol

## No foundation-model training. What *is* fitted:
| Component | Method | Data | When |
|---|---|---|---|
| Per-model reward predictors (adaptive bandit) | Ridge regression, online batch refit | scored outcomes of the selected action | Phase 8 calibrate → Phase 9 online |
| Frozen supervised router (baseline) | Same ridge/regression (optionally gradient boosting as sensitivity) trained once on the **train split with all-model outcomes**, then frozen | oracle-subset + calibration outcomes | Phase 9 |
| Feature scaler, regularisation λ, window W, ε schedule | tuned on dev split | dev | Phase 9 |
| Privacy detector thresholds | grid search on synthetic dev set (precision/recall) | synthetic privacy suite dev part | Phase 4/8 |
| Complexity estimate | heuristic features (no learned model in MVP) | – | Phase 5 |

## Dataset build (`eval/build_dataset.py`)
Workload (from proposal): 360 document QA (curated QASPER) · 120 summaries/explanations · 120 context/failure stress · 200 synthetic privacy tests. Public/licensed papers only; synthetic identifiers only. Each item: `doc_id, task_type, prompt, reference/evidence, label, split`.
Split **by source document** 60/20/20 (train/dev/test); paraphrases and privacy variants stay together. Freeze `splits.json` with a hash.

## Pipeline order (Makefile targets)
1. `make eval-build` — dataset + splits.
2. `make eval-pilot` — price/latency pilot → fix `C_ref`, `L_ref`, estimate cost per run.
3. `make eval-oracle` — public 120-request subset run through **all three** models (empirical oracle; learner never sees non-selected outcomes during replay).
4. `make eval-score` — automatic scores (F1, evidence checks, rubric coverage).
5. Blind human rating: 120 stratified responses × 2 raters × 4 dimensions via `/rate`. Compute agreement (Cohen's κ / weighted κ) and source bias.
6. `make eval-calibrate` — ~50 scored non-sensitive examples per model → initial θ_a.
7. `make eval-train-frozen` — frozen supervised baseline.
8. Freeze models, prices, features, thresholds, scoring (git tag `eval-freeze-N`).
9. `make eval-static` — static test: local-only, strong-cloud-only, fixed rules, frozen, adaptive on test split with shared constraints/evidence. Seeds ≥3.
10. `make eval-stream` — separate stream with controlled task or latency shift; predict first, update after (replay engine).
11. `make eval-privacy` — 200 privacy tests: detector precision/recall **and** unauthorized-dispatch count (separate metrics).
12. `make eval-stats` — document-clustered bootstrap 95% CIs, regret (oracle subset only), ablations (weights, frozen vs adaptive, feature ablations).

## Metrics to emit
Quality by task · mean API cost incl. retries/aux calls · median/p95 latency · TTFT · routing overhead (<500 ms warm target) · token use · failures · local-route share · abstention + ineligibility rate on mixed workload · detector P/R · unauthorized dispatches (target 0 in suite) · regret.
Primary target: ≥20% lower API cost than strong-cloud-only on matching cloud-eligible requests, with lower CI bound of paired quality difference > −0.05. Report unmet/inconclusive honestly; "rules suffice" is a valid finding.

## Rules
Never tune on test. Record seed, git SHA, config hash, price snapshot, model IDs in `eval_runs`. Every experiment script is idempotent and cached by (item, model, prompt-hash) to avoid paying twice. Hard-stop at budget (admin eval key).