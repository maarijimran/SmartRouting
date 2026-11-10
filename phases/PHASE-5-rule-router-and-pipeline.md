# PHASE 5 — Rule router + end-to-end gateway pipeline  (proposal A3 · FYP1 baseline demo, Dec 2026)
**Goal:** a complete working turn: question → evidence → eligibility → route → answer → metrics. Fixed rules only.
**Prereqs:** Phases 2, 3, 4. **Read:** docs/01 (workflow, policy interface, rules), docs/05.

## Tasks
- [ ] `routing/features.py`: feature extraction (docs/05 list) with estimated tokens/cost/latency per candidate.
- [ ] `routing/eligibility.py`: composes privacy, health, context, hardware, budget, key/price checks → `(eligible, removed[{model,reason}])`.
- [ ] `routing/rules.py` + `configs/routing.yaml`: ordered, explainable rules returning rule ID; baselines `local_only` and `strong_cloud_only` (same constraints).
- [ ] `routing/policy_store.py`: `policy_versions` CRUD; active policy per deployment; rules = version 0 (rollback target).
- [ ] `gateway/pipeline.py`: implement the 17-step workflow; abstain path; bounded retry that re-enters eligibility; no mid-generation switch.
- [ ] `POST /sessions/{id}/chat` SSE: `route`, `token`, `compression_notice`, `done`, `abstain`, `error`.
- [ ] Persist `routing_events` + `attempts` (scrubbed); expose measured vs estimated separately.
- [ ] Minimal chat page wired to SSE (enough for the December demo); full UI in Phase 6.

## Acceptance
E2E on fake adapters and manual run on real local + 2 cloud models: doc QA and summary both work · every request shows model, reason, tokens, cost, latency, status · abstain when no route allowed · local-only never reaches cloud · budget stop · routing overhead measured (warm, excl. ingestion/generation) and recorded vs 500 ms target · FYP1 demo script `docs/demo-fyp1.md`.
