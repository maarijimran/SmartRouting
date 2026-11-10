# PHASE 0 — Bootstrap + hardware & pricing pilot  (proposal A1 · Aug–Sep 2026; catch-up now)
**Goal:** runnable skeleton + facts needed to freeze the stack.
**Prereqs:** none. **Read:** CLAUDE.md, docs/01.

## Tasks
- [ ] Create monorepo layout from CLAUDE.md; `.gitignore`, `.env.example` (DB URL, JWT secret, `KEY_VAULT_MASTER_KEY`, OLLAMA_URL, ADMIN_EMAIL).
- [ ] `docker-compose.yml`: postgres, ollama, backend, frontend. `Makefile` targets from CLAUDE.md.
- [ ] FastAPI app with `/healthz`; Alembic initialised; Next.js app boots; GitHub Actions runs lint + a smoke test.
- [ ] `import-linter` config encoding module boundaries (docs/01) and the adapter rule.
- [ ] Scrubbing logger (`core/logging_scrub.py`) with canary tests.
- [ ] **Hardware pilot** `scripts/profile_local.py`: for 2–3 candidate 7–8B 4-bit models (+ a ~3B fallback) record RAM/VRAM, load time, tokens/s, max usable `num_ctx` on the 8 GB GPU. Write `docs/pilot-hardware.md`; pick the local model.
- [ ] **Pricing pilot** `scripts/price_pilot.py` (admin key, ≤ USD 15): pick cheap + strong OpenRouter models; record dated prices, measured latency, whether usage/cost is returned per call; derive provisional `C_ref`, `L_ref` → `configs/reward.yaml`.
- [ ] Fill `configs/models.yaml` with chosen models (ids, context limits, tokenizer, price snapshot date).

## Acceptance
`make up` starts all services · `make test` green in CI · pilot docs committed with numbers · stack versions frozen in `docs/stack-freeze.md`.
**Out of scope:** auth, any routing logic.
