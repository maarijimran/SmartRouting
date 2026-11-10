# Frozen evaluation plan (DRAFT — to be reviewed by all three members and the supervisor)

Status: **draft**. It becomes the frozen plan when every `TODO(team)` below is resolved, the
review is recorded in `PROGRESS.md`, and git tag `eval-freeze-0` is created. Until then no result
may be reported as final. The harness (`eval/`) implements this plan; `docs/06` is the pipeline
specification.

## Research questions and targets (hypotheses, not results)
- **Primary:** on matching cloud-eligible requests, adaptive routing reaches ≥ 20% lower API cost
  than `strong_cloud_only` while the lower bound of the 95% CI of the paired quality difference is
  > −0.05. Unmet or inconclusive outcomes are reported as such; "fixed rules suffice" is valid.
- **Privacy:** 0 unauthorised dispatches in the 200-case synthetic suite; detector precision and
  recall reported separately (a detector miss and a gate pass are different failures).
- **Overhead:** warm median routing overhead < 500 ms (`perf-latest.json`, per-event
  `routing_latency_ms`).

## Workload and splits
360 document-QA (curated QASPER) · 120 summaries/explanations · 120 context/failure stress · 200
synthetic privacy tests. Public/licensed papers only; synthetic identifiers only. Split **by
document** 60/20/20 (paraphrase and privacy-variant groups stay together); `splits.json` carries a
SHA-256 and `eval.splits.check_leakage` runs in CI. TODO(team): confirm the QASPER licence and the
curation rule for the 360 questions; record both in `datasets/<name>/licences.json`.

## Policies compared (shared evidence, shared eligibility)
`local_only`, `strong_cloud_only`, `fixed_rules`, `frozen_supervised`, `adaptive_bandit`.
Confidential/internal-labelled items exercise the shared constraint: cloud is ineligible, so
`strong_cloud_only` abstains (reported as abstention rate, never silently routed).

## Quality and reward
Automatic score A: QA token-F1 (+ 0.2 evidence overlap); summaries/explanations rubric-key-point
coverage (`eval/rubric.md`). Human score H from the blind 4×(1–5) rubric, 120 stratified responses ×
2 raters; agreement via weighted κ and a source-bias report before pooling. Q = 0.7H + 0.3A when
both exist. Reward R = 0.5Q + 0.3(1−min(C/C_ref,1)) + 0.2(1−min(L/L_ref,1)); failures R = −1.
TODO(team): C_ref and L_ref from the pricing pilot (`price_pilot.py --write-reward`), then set
`frozen: true` in `configs/reward.yaml`. TODO(team): decide whether an LLM judge is used for A
(non-sensitive items only, validated against H) — not implemented.

## Procedure (Makefile order; `docs/06` has the detail)
1. `eval-build` → 2. `eval-pilot` (price/latency) → 3. `eval-oracle` (all 3 models, public
subset; the learner never sees non-selected outcomes during replay) → 4. scores → 5. human rating →
6. `eval-calibrate` (~50 non-sensitive train examples per model) → 7. `eval-train-frozen` → 8.
**freeze** (tag `eval-freeze-N`; models, prices, features, thresholds, scoring) → 9. static test on
the test split, ≥ 3 seeds → 10. stream test with a controlled latency shift (predict first, update
after) → 11. privacy suite → 12. statistics. Tune only on dev; never on test.

## Statistics
Document-clustered bootstrap (2,000 resamples, seed recorded) for means, paired differences and
cost reduction. Off-policy IPS / doubly-robust estimates from the logged propensities complement
oracle-subset regret. Ablations: reward-weight sensitivity, frozen vs adaptive, feature groups, ε
schedule.

## Budget (USD 100 cap; `configs/budget.yaml`)
Pilot 15 · benchmark 55 · adaptive 15 · contingency 15. Every live call is cached and hard-stops at
the cap (`eval/executor.py::BudgetGuard`, persisted ledger). The report's `budget` section shows
projected vs spent.

## Reproducibility record (written by `eval.run_all` into every report)
Seeds, git SHA, hash of all `configs/*.yaml`, model IDs, price snapshot, reward config, splits hash,
and whether the run was `SIMULATED` or `live`.

## Ethics and approval note
Human raters rate synthetic or public material only; no student documents are used. Departmental
approval for rating is not required (decision log). TODO(team): record supervisor confirmation.
