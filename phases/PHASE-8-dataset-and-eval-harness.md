# PHASE 8 — Dataset, evaluation harness, calibration  (proposal M1/M2 · Aug–Dec 2026, finishes FYP1)
**Goal:** frozen evaluation protocol + scored development data.
**Prereqs:** Phase 5 (pipeline), Phase 7 scorers. **Read:** docs/06 fully.

## Tasks
- [ ] `eval/build_dataset.py`: curate QASPER subset (360), summaries/explanations (120), stress (120), privacy suite import (200); licences recorded; synthetic identifiers only.
- [ ] Group-by-document 60/20/20 split; `splits.json` + hash; leakage test (no doc in two splits, paraphrase groups intact).
- [ ] `eval/run_baselines.py` (shared evidence/constraints) with result cache keyed by (item, model, prompt-hash, config-hash).
- [ ] `eval/oracle.py`: all-3-model outcomes on 120-request public subset.
- [ ] Rating collection plan + rubric doc `eval/rubric.md`; ethics/approval note.
- [ ] `eval/calibrate.py`: ~50 scored non-sensitive examples per model → initial regressors (artifact saved with version).
- [ ] Fix `C_ref`, `L_ref`, reward weights in `configs/reward.yaml`; write **frozen evaluation plan** `docs/eval-plan.md`; tag `eval-freeze-0` after dev tuning.
- [ ] Budget sheet: projected vs spent per bucket (15/55/15/15).

## Acceptance
`make eval-smoke` runs a 10-item slice end-to-end for all baselines · split leakage test passes · cached reruns cost USD 0 · plan reviewed by all three members and supervisor.
