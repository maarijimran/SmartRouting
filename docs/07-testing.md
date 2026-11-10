# 07 — Testing strategy

Use a **FakeAdapter** (deterministic latency/cost/failure injection) and a **fake egress sink** that records every outbound payload. No test calls a real cloud API.

## Privacy regression suite (`backend/tests/privacy/`, runs in CI, blocks merge)
- local-only mode: zero cloud actions for any input, including with detector disabled.
- confidential label blocks cloud even with no entities detected.
- sensitive entity in: prompt / document chunk / history / summary / retrieved evidence → cloud blocked without scoped consent.
- consent scope: wrong model, changed payload hash, expired, revoked → blocked. Institutional prohibition overrides consent.
- scanner exception → cloud blocked (fail closed).
- retry/fallback after a local failure re-checks eligibility (local-only request never retried on cloud).
- derived content inherits label (compressed summary of confidential doc stays confidential).
- benign lookalikes (e.g. "03-2024" dates, paper IDs) don't over-block beyond the agreed threshold.
- egress spy: assert fake sink never receives a seeded canary PII string in the blocked scenarios.
- import-linter: adapters not importable outside `gateway/`.

## Security tests
Cross-user isolation (sessions, docs, keys, feedback) · key never in any API response/log (grep canary) · JWT expiry/refresh rotation/revocation · rate-limit/lockout · upload size/page limits · malicious doc text cannot change policy.

## Unit / integration
Parsers (digital PDF, TXT, corrupt PDF → clear 422) · chunking/BM25 · token counting + context fit · eligibility table · reward math · bandit update + probability logging · policy versioning/rollback · budget reserve/settle · pipeline end-to-end with each policy · SSE contract.

## E2E (Playwright, Phase 6+)
Register → login → add key (fake provider) → upload → ask → see route explanation → abstain case → feedback → analytics.

## CI
GitHub Actions: lint (ruff, mypy, eslint) → unit → privacy → integration (compose db) → frontend build. Coverage target ≥80% on `privacy/`, `routing/`, `gateway/`.