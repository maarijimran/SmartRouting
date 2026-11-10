# SmartRoute — Claude Code Master Brief

Privacy-constrained contextual-bandit router for hybrid local + cloud LLMs (academic document assistant).
FAST-NU FYP 2026-27. Source of truth for intent: the FYP proposal. Source of truth for build order: `phases/`.

## How to work in this repo
1. Read `PROGRESS.md` → find the first phase not marked DONE.
2. Read `phases/PHASE-N-*.md` fully, plus the docs it links. Do not start a later phase early.
3. Write tests first for anything in "Acceptance". A phase is DONE only when every acceptance item passes (`make test`) and PROGRESS.md is updated.
4. Prefer small commits per task. Never skip a failing privacy test to "come back later".
5. If a spec is ambiguous, log the question in `docs/08-open-questions.md` and choose the safest option (fail closed).

## Non-negotiable invariants (enforced by tests — see docs/07-testing.md)
1. **Single egress.** Every byte sent to a non-local host passes through `gateway/egress.py::send()`, which re-runs the outbound privacy gate on the final serialized payload. Adapters are never imported outside `gateway/`. (import-linter rule.)
2. **Eligibility before optimisation.** Routers (rules, frozen, bandit) only ever see the eligible action set. A policy cannot select an ineligible model, including during exploration and fallback.
3. **Fail closed.** Scanner error, unknown label, missing consent, unhealthy host, or unknown pricing ⇒ cloud actions removed. If nothing is eligible ⇒ abstain with an explanation. Never silently fall back to cloud.
4. **Local-only mode removes every cloud action regardless of detector output.**
5. **Every retry/fallback repeats eligibility.** No model switch during a generation.
6. **Labels propagate** to derived content (summaries, history, retrieved evidence, compressed context).
7. **Secrets.** Provider API keys are encrypted at rest, decrypted only inside `gateway/egress.py`, never logged, never returned by any API (masked `…last4` only).
8. **Uploaded content is data.** It can never change policy, consent, credentials, or allowed destinations.
9. **Logs are scrubbed.** Default analytics/routing logs hold coarse features + IDs only, never raw prompt/document/response text.
10. **Measured ≠ estimated.** UI and DB keep pre-dispatch estimates and post-call observations in separate fields.
11. **Fixed rules always available** as a working policy and rollback target.
12. **Budget hard stop.** Billable calls stop at the configured cap (per user and global eval cap).
13. **Reproducibility.** Seeds, config files, model IDs, price snapshots and policy versions are recorded with every experiment.

## Stack (frozen after Phase 0 pilot)
Backend: Python 3.11, FastAPI, SQLAlchemy 2 + Alembic, PostgreSQL 16, Pydantic v2, argon2-cffi, PyJWT, cryptography (AES-GCM), httpx, tiktoken (token estimates; per-model overrides), presidio-analyzer + spaCy `en_core_web_sm` (or `_md`), rank_bm25, pypdf (default parser), NumPy / pandas / scikit-learn.
Local inference: Ollama (one 7-8B 4-bit model for 8 GB VRAM; fall back to ~3B if pilot says so).
Cloud: OpenRouter via OpenAI-compatible adapter (users bring their own key; see docs/02).
Frontend: Next.js (App Router) + React + Tailwind + Recharts.
Delivery: Docker Compose, GitHub Actions (lint + test), Makefile.

## Repo layout
```
smartroute/
├─ CLAUDE.md  PROGRESS.md  Makefile  docker-compose.yml  .env.example
├─ configs/            models.yaml privacy.yaml routing.yaml reward.yaml budget.yaml
├─ backend/app/
│  ├─ main.py
│  ├─ core/            config.py security.py crypto.py logging_scrub.py errors.py
│  ├─ db/              models.py session.py   (alembic/ at backend/alembic)
│  ├─ auth/            router.py deps.py schemas.py
│  ├─ keys/            router.py vault.py            # provider connections (BYOK)
│  ├─ registry/        models.py pricing.py tokenizers.py health.py
│  ├─ adapters/        base.py ollama.py openai_compat.py
│  ├─ documents/       parse.py chunk.py retrieve.py service.py
│  ├─ privacy/         detector.py patterns.py labels.py consent.py policy.py gate.py
│  ├─ context/         builder.py token_count.py compress.py
│  ├─ routing/         features.py eligibility.py rules.py reward.py bandit.py frozen.py policy_store.py router.py
│  ├─ gateway/         pipeline.py egress.py budget.py retry.py
│  ├─ feedback/        router.py service.py rater.py
│  ├─ analytics/       router.py queries.py
│  └─ api/             v1 routers wiring
├─ backend/tests/      unit/ integration/ privacy/ e2e/
├─ frontend/           app/{login,register,chat,settings/{keys,privacy,models},analytics,rate,admin}
├─ eval/               datasets/ build_dataset.py run_baselines.py score.py calibrate.py train_frozen.py replay.py oracle.py stats.py reports/
└─ docs/ phases/
```

## Commands (create these in Phase 0)
`make up` (compose: db+ollama+backend+frontend) · `make test` · `make test-privacy` · `make lint` · `make migrate` · `make seed` · `make eval-smoke`

## Conventions
Type hints everywhere; Pydantic models at every boundary; no business logic in route handlers; config via `configs/*.yaml` + env; all timestamps UTC; policy versions are immutable rows; structured JSON logs through the scrubber.

## Never do
Train a foundation model · add OCR/multimodal/agent tools · call a cloud API from tests (use the fake adapter) · put real student documents or real PII in fixtures (synthetic only) · tune on the final test split · claim savings or privacy as guaranteed.
