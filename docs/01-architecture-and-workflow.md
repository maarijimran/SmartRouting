# 01 — Architecture and end-to-end workflow

## Tiers
- **Presentation** (Next.js): auth pages, chat, upload, privacy mode + doc labels, route explanation, metrics (observed vs estimated), feedback, key management, analytics, rater UI, admin.
- **Application** (FastAPI): auth, key vault, registry, documents, privacy, context, routing, gateway, feedback, analytics.
- **Data** (PostgreSQL): see 03-data-model.md. Raw session content lives only in active-session tables with expiry.

**Trusted boundary** = the backend host + local Ollama. Everything leaving it goes through `egress.send()`.

## Request workflow (one chat turn) — implement exactly in `gateway/pipeline.py`
```
 1. AUTH        validate JWT → user, role
 2. VALIDATE    prompt/doc type, size (10 MB, 100 pages), user cost preference, privacy mode
 3. LABEL       effective_label = max(user mode, doc label, session label, institutional policy)
 4. EVIDENCE    (local) parse → chunk → BM25 retrieve top-k for the question
 5. DETECT      scan prompt + chunks + history + summaries; record coarse findings (type, count; no text)
 6. PAYLOAD     per candidate model: build provider-independent messages → fit context
                (reserve output + safety margin; local compression with visible notice)
 7. ESTIMATE    candidate-specific input/output tokens, est. cost (price snapshot), est. latency
 8. ELIGIBILITY remove: privacy-blocked, no key/consent, unhealthy, context-infeasible,
                hardware-infeasible, over budget, unknown price   → action set A
 9. IF A empty  → ABSTAIN: explain which constraint(s) removed everything. STOP. Log event.
10. FEATURES    x = task type, tokens, retrieval stats, mode, cost pref, recent per-model latency/failure
11. SELECT      policy ∈ {rules, frozen, bandit} picks a ∈ A; log P(a|x), policy_version, epsilon
12. OUTBOUND    serialize final payload for a → egress gate re-scan (cloud only) → pass/block
13. GENERATE    adapter streams tokens (SSE) ; capture TTFT, latency, usage, measured cost
14. ON FAILURE  record attempt (R=-1, incurred cost) → rerun steps 8–12 on the remaining set → bounded retries
15. RECORD      routing_event + attempts (scrubbed), metrics, provenance
16. FEEDBACK    optional 4×(1–5) ratings + auto score → Q → R → buffered for batch update
17. LEARN       every 50 scored outcomes (selected-action only) → new immutable policy version; rollback available
```

## Module boundaries (who may import whom)
`api → gateway → {routing, privacy, context, documents, registry, adapters(only via egress)}`; `routing` knows nothing about adapters; `privacy` knows nothing about routing; `adapters` know nothing about the DB. Enforce with import-linter.

## Policies behind one interface
```python
class Policy(Protocol):
    name: str; version: str
    def select(self, x: Features, eligible: list[ModelId]) -> Decision  # Decision(action, prob, explanation)
    def update(self, batch: list[ScoredOutcome]) -> "Policy"            # no-op for rules / frozen
```
Policies: `local_only`, `strong_cloud_only`, `fixed_rules`, `frozen_supervised`, `adaptive_bandit`. All share the same pipeline, evidence and constraints.

## Fixed-rule baseline (explainable; write as ordered rules in configs/routing.yaml)
1. effective_label forbids cloud → local.
2. est. prompt tokens > local context limit → eligible cloud only.
3. task ∈ {definition, short explanation} and short evidence → local.
4. task = cross-section QA or evidence spread across >N chunks → strong cloud.
5. otherwise → cheap cloud; user cost-pref "lowest" biases to local when eligible.
Each decision returns the rule ID that fired (shown in UI).

## Abstention and explanation UX
Every block states: which constraint, which models it removed, what the user can do (change mode, add key, shorten doc). Never "something went wrong".