# PHASE 7 — Logging, feedback, blind rating, analytics  (proposal T3 · Jan–Mar 2027)
**Goal:** trustworthy scored outcomes and visible metrics.
**Prereqs:** Phase 5. **Read:** docs/03 (feedback, scored_outcomes), docs/05 (reward), docs/06.

## Tasks
- [ ] `feedback/service.py`: store 4×(1–5) ratings with source (user/rater/auto), compute H, Q (with `q_source`), R; write `scored_outcomes`; skip privacy-blocks; failed attempts R=-1 with incurred cost.
- [ ] Automatic scorers `eval/score.py` as importable lib: token-F1/EM, evidence overlap, summary rubric coverage; (optional) frozen LLM-judge for non-sensitive items, validated against human ratings.
- [ ] Rater workflow: queue of 120 stratified responses, model identity hidden, assignment to 2 raters, agreement (κ) report, feedback-source bias report.
- [ ] Analytics endpoints + `/analytics`: cost, p50/p95 latency, TTFT, local share, failures, quality by task/model, abstention, privacy counters; CSV/JSON export (admin).
- [ ] Retention jobs: raw content 60 min, metadata 30 days, export before purge for eval runs (synthetic/public only).

## Acceptance
Reward unit tests match worked examples in docs/05 · deferral when no quality signal · blind UI leaks no model info (test inspects payload) · aggregates equal hand-computed fixtures · retention jobs verified.
