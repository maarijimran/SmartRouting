# PHASE 6 — Frontend  (proposal T1/T3)
**Goal:** full user-facing product per docs/04. Start the minimal slice in Phase 5, finish here.
**Prereqs:** Phase 5 API stable (OpenAPI schema frozen; generate TS client from it).

## Tasks
- [ ] Generate typed client from FastAPI OpenAPI.
- [ ] `/chat`: session list, mode toggle, doc upload + label chip, cost preference, streaming answer, **Route panel**, consent dialog (destination + redacted payload preview), abstain explanation, compression notice, retry trail, feedback widget.
- [ ] `/settings/models`, `/settings/privacy` (retention, delete-all, consents), polish `/settings/keys`.
- [ ] `/admin`: registry/prices, institutional policy, policy versions + rollback, budgets, users.
- [ ] States: loading/empty/error everywhere; responsive; keyboard + contrast accessible.

## Acceptance
Playwright E2E from docs/07 passes against fake provider · estimated vs observed always shown in separate fields · privacy state visible in header · no key ever rendered after save · Lighthouse a11y ≥ 90 on main pages.
