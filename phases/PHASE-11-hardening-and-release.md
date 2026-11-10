# PHASE 11 — Hardening, documentation, reproducible release  (proposal A4/T4 · Apr–May 2027)
## Tasks
- [ ] Performance tests: routing overhead (<500 ms warm median target), concurrency for small lab, upload limits; record test machine.
- [ ] Privacy regression full run + security review checklist (keys, isolation, headers, rate limits, dependency audit).
- [ ] Reproducibility: pinned lockfiles, `docker compose up` from clean clone, seed data, versioned configs, one-command `make eval-all`.
- [ ] Docs: README, deployment guide, user guide, admin guide, API docs, architecture diagrams, limitations (detector limits, hardware dependence, small English academic dataset), ethics statement.
- [ ] Demonstration script covering: both core tasks, context continuity, local-only, confidential block + consent, abstain, fallback, policy rollback, analytics.
- [ ] Tag `v1.0.0`; archive evaluation artefacts.
- [ ] Stretch (only after core benchmark complete): extra provider adapters, second bandit, translation/coding tasks, multilingual NER.

## Acceptance
Fresh machine follows the deployment guide and reaches a working demo · all CI gates green · final report numbers trace to saved run IDs.
