# PHASE 2 — Model registry, adapters, health, budgets, retries  (proposal A2)
**Goal:** one common interface to the local model and two cloud models, with cost/health controls.
**Prereqs:** Phase 1. **Read:** docs/01 (module boundaries), docs/03 (registry, attempts), docs/02 (budget).

## Tasks
- [ ] `adapters/base.py`: `generate(messages, params) -> AsyncIterator[Chunk]`, `health()`, `count_tokens()`, normalised errors, usage + TTFT capture.
- [ ] `adapters/ollama.py` (local, `num_ctx` set explicitly) and `adapters/openai_compat.py` (OpenRouter/custom base URL; streaming; reads usage/cost when provided, else computes from price snapshot).
- [ ] `adapters/fake.py` for tests: scripted latency, cost, failures, empty/truncated outputs.
- [ ] `gateway/egress.py::send()`: the only caller of cloud adapters; decrypts key, calls outbound gate (stub PASS until Phase 4 — guarded by a `PRIVACY_GATE_REQUIRED=true` startup assertion that fails if the real gate is missing in non-test mode).
- [ ] `registry/`: models, price snapshots with timestamps, tokenizer selection, background health checks, hardware headroom check for local.
- [ ] `gateway/budget.py`: reserve → settle ledger; refuse on cap; global eval cap.
- [ ] `gateway/retry.py`: bounded retries (default 1), timeouts, failure classification (R=-1 classes), **re-entry to eligibility** hook.
- [ ] Admin endpoints for registry + prices; user endpoint to pick cheap/strong model from their connection.
- [ ] Real connection test now uses egress + adapter.

## Acceptance
Fake-adapter integration tests for success/timeout/empty/truncated · budget stop works mid-batch · unknown price ⇒ model not eligible · health flap removes/restores model · local model call works against real Ollama in a manual smoke (`make smoke-local`) · import-linter passes.
