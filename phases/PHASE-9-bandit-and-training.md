# PHASE 9 — Bandit, frozen baseline, training pipeline  (proposal M3 · Jan–Feb 2027)
**Goal:** adaptive router with bounded, eligibility-constrained exploration, versioning and rollback.
**Prereqs:** Phase 4 DONE (privacy gate in CI), Phase 7 (scored outcomes, stable logging), Phase 8 (calibration). **Read:** docs/05 (bandit, reward), docs/06.

## Tasks
- [ ] `routing/bandit.py`: per-model ridge reward predictor, scaler fit on train only, ε-greedy over the **eligible** set, true action probability logging, ε schedule 0.10→0.02 over 1,000 scored decisions.
- [ ] `routing/frozen.py` + `eval/train_frozen.py`: supervised router trained once on train split, frozen.
- [ ] Online learner: buffer scored outcomes; update every 50; only selected action's feedback; new immutable `policy_versions`; optional sliding window.
- [ ] Cold-start handoff: fixed rules until ≈50 scored examples/model.
- [ ] Shadow mode (docs/08 #1): bandit logs counterfactual choice while rules serve.
- [ ] Rollback: admin button + automatic triggers (reward drop, privacy incident, error spike).
- [ ] `eval/replay.py`: predict-then-update replay engine; learner sees only selected-action outcomes; supports controlled task/latency shift.
- [ ] Tune features, λ, window on dev split only; save configs.

## Acceptance
Property tests: bandit never returns an ineligible model; logged probabilities sum to 1 over eligible set · update uses only selected-action data · rollback restores previous behaviour exactly · replay deterministic by seed · exploration disabled for cloud if privacy CI gate red · bandit ≥ fixed rules not required, but results must be reproducible.
