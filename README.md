# SmartRoute

Privacy-constrained contextual-bandit routing between a local model (Ollama) and cloud models
(OpenRouter) for academic document assistance. FAST-NU FYP 2026-27.

Every chat turn: privacy label → local evidence retrieval → privacy scan → per-model payload →
**eligibility** (privacy, consent, health, context, budget, price) → policy picks from the
eligible set only → single egress point re-scans the final payload → stream, measure, log.

| Policy | Purpose |
|---|---|
| `local_only`, `strong_cloud_only` | baselines (same constraints) |
| `fixed_rules` (version 0) | explainable baseline, always available, rollback target |
| `frozen_supervised` | ridge predictors trained once on the train split |
| `adaptive_bandit` | ε-greedy over eligible set, per-model ridge, batch updates, shadow mode, rollback |

## Quick start (laptop, no GPU, no API keys)

```powershell
python -m venv .venv ; .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:FAKE_PROVIDERS = "true"          # every model is a deterministic fake
$env:KEY_VAULT_MASTER_KEY = python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"
python scripts/seed_demo.py
python -m uvicorn app.main:app --app-dir backend --port 8000
```

Then in another terminal (needs Node 22): `cd frontend ; npm install ; npm run dev` and open
<http://localhost:3000>. Full instructions, including Ollama on a GPU machine and testing a real
free cloud key, are in **[SETUP.md](SETUP.md)**.

## Checks

```powershell
python -m pytest                 # 110+ tests, no network, no provider calls
python -m ruff check backend scripts eval
lint-imports                     # adapters only importable inside gateway/
python -m eval.privacy_suite     # privacy regression gate (also blocks cloud exploration at runtime)
python -m eval.run_all           # simulated end-to-end evaluation pipeline (NOT a result)
```

## Where things are

`CLAUDE.md` rules · `PROGRESS.md` honest phase status · `SETUP.md` setup · `docs/` specs, eval
plan, guides, limitations · `phases/` task lists · `backend/app` API · `eval/` evaluation harness ·
`frontend/` Next.js app · `configs/` YAML configs · `scripts/` pilots and utilities.
