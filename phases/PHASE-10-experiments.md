# PHASE 10 — Experiments, ablations, statistics  (proposal M4 · Mar–Apr 2027)
**Prereqs:** Phase 9; evaluation frozen (`eval-freeze-N` tag). **Read:** docs/06.

## Tasks
- [ ] Static test: local-only, strong-cloud-only, fixed rules, frozen supervised, adaptive — shared constraints/evidence; ≥3 seeds.
- [ ] Controlled-change stream (task mix or latency shift): predict first, update after.
- [ ] Privacy suite run: detector precision/recall and unauthorized-dispatch counts reported separately.
- [ ] Oracle subset: empirical regret; (optional) IPS / doubly-robust estimates from logged propensities.
- [ ] Ablations: reward weights sensitivity, frozen vs adaptive, feature ablations, ε schedule.
- [ ] `eval/stats.py`: document-clustered bootstrap 95% CIs; paired quality difference vs strong-cloud-only; cost reduction CI.
- [ ] Error analysis notebook: failure categories, abstentions, privacy false positives/negatives.
- [ ] Report all targets honestly (≥20% cost reduction with quality lower bound > −0.05; zero unauthorized dispatches in suite).

## Acceptance
All tables/figures regenerate from `make eval-all` using frozen configs and cached outputs; results saved in `eval/reports/` with run IDs, SHAs, price snapshots.
