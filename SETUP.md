# SmartRoute setup guide

This is the living setup guide for the SmartRoute FYP project. Update this
file whenever a phase adds a dependency, environment variable, migration,
service, or validation command.

## Current status

See `PROGRESS.md` for the honest per-phase status. In short: the backend (auth, vault, registry,
documents, privacy, routing, bandit, feedback, analytics, evaluation harness) is built and tested
on fake providers; the frontend is written but has not been built on this project's dev laptop
(no Node there); Ollama setup, the hardware/pricing pilots and real-provider runs are waiting
for the GPU machine and an API key.

## Prerequisites

Required for backend development:

- Python 3.11 or newer
- Git
- A virtual environment is recommended

Required for the full Compose stack:

- Docker Desktop with Docker Compose
- Node.js and npm for local frontend development

Required only on the GPU machine (local model):

- Ollama (native, or the `local-llm` Compose profile)
- Candidate models downloaded with `ollama pull`
- About 8 GB VRAM and 16 GB RAM for a 7–8B 4-bit model

## Initial setup

From the project root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Edit `.env` before starting the application:

- `DATABASE_URL`: PostgreSQL URL for Docker, or SQLite for local-only tests.
- `JWT_SECRET`: random secret of at least 32 characters.
- `KEY_VAULT_MASTER_KEY`: base64-encoded 32-byte key.
- `OLLAMA_URL`: Ollama service URL.
- `FRONTEND_ORIGIN`: allowed frontend origin.
- `ADMIN_EMAIL`: optional email that receives the admin role.

Never commit `.env`, provider keys, real documents, or real personal data.

## Database

Apply migrations:

```powershell
python -m alembic upgrade head
```

Phase 3 migrations add sessions, documents, chunks, and messages.

The default local configuration uses SQLite. Docker Compose provides PostgreSQL
at `localhost:5432` and configures the backend to use it.

## Validation

Run backend tests:

```powershell
python -m pytest
```

Run lint:

```powershell
python -m ruff check backend scripts
```

Start the complete stack when Docker Desktop is available:

```powershell
docker compose up --build
```

Expected services:

- Backend: `http://localhost:8000`
- Health endpoint: `http://localhost:8000/healthz`
- Frontend: `http://localhost:3000`
- PostgreSQL: `localhost:5432`
- Ollama (only with `--profile local-llm`): `http://localhost:11434`

Stop the stack:

```powershell
docker compose down
```

## Local model (Ollama) setup — do this on the GPU machine

The development laptop cannot run a 7–8B model, so Ollama setup is deferred to a
machine with a suitable GPU (target: 8 GB VRAM, 16 GB RAM). Nothing else in the
project needs Ollama; without it, local models simply show as unhealthy and the
router fails closed (cloud still works only if consent/privacy allow it).

There are two ways to run it. Pick one.

**Option A — everything on the GPU machine (simplest).**

1. Install Docker Desktop (with NVIDIA GPU support) or install Ollama natively.
2. Native Ollama: download from <https://ollama.com/download>, then it runs on
   `http://localhost:11434`. Docker: `docker compose --profile local-llm up --build`
   (the `local-llm` profile starts the bundled `ollama` container).
3. Leave `OLLAMA_URL` as `http://localhost:11434` for native, or
   `http://ollama:11434` for the Compose container (the default).

**Option B — Ollama on the GPU machine, app on the laptop.**

1. On the GPU machine, make Ollama listen on the network:
   `setx OLLAMA_HOST 0.0.0.0:11434` (Windows; restart Ollama) or
   `OLLAMA_HOST=0.0.0.0:11434 ollama serve` (Linux/macOS). Allow TCP 11434
   through the firewall for your LAN only. Do not expose it to the internet.
2. On the laptop, set `OLLAMA_URL=http://<gpu-machine-ip>:11434` in `.env`.
3. Run the stack **without** the `local-llm` profile: `docker compose up --build`.

### Steps on the GPU machine

1. Pull the candidate models (the plan profiles 2–3 at 7–8B 4-bit plus a ~3B fallback):

   ```powershell
   ollama pull llama3.1:8b-instruct-q4_K_M
   ollama pull qwen2.5:7b-instruct-q4_K_M
   ollama pull llama3.2:3b-instruct-q4_K_M
   ollama list
   ```

   Tags change over time; if a pull fails, pick the nearest 4-bit tag from
   <https://ollama.com/library>.

2. Confirm Ollama answers: `curl http://localhost:11434/api/tags`.
3. From the project root, with the venv active (`pip install -e ".[dev]"`):

   ```powershell
   python scripts/profile_local.py --model llama3.1:8b-instruct-q4_K_M --model qwen2.5:7b-instruct-q4_K_M --model llama3.2:3b-instruct-q4_K_M
   ```

   Use `--url http://<ip>:11434` if Ollama is on another host, and `--num-ctx`
   to test a different context size (default 8192; try 4096 if a model spills
   out of VRAM). The script cold-loads each model and records load time,
   tokens/second, VRAM used and whether it fits fully on the GPU, into
   `docs/pilot-hardware.json`. It only records what Ollama reports; if Ollama or
   a model is missing it stops with an error and writes nothing.
4. Copy the numbers into `docs/pilot-hardware.md`, choose the local model, then
   edit `configs/models.yaml` (`local-pilot` slug/tag, `context_limit`).
5. Mark Phase 0 done in `PROGRESS.md` and update the status list above.

Cloud models need no GPU, so the laptop can test them any time; see below.

## Testing a cloud model with a free API key

`scripts/cloud_smoke.py` sends one synthetic prompt to any OpenAI-compatible
endpoint and prints latency and the usage fields the provider returns. Keys are
read from environment variables, never command-line arguments.

| Provider | Key from | Env var | Notes |
|---|---|---|---|
| OpenRouter (recommended; this is the project's real provider) | <https://openrouter.ai/keys> | `OPENROUTER_API_KEY` | Models whose ID ends in `:free` cost nothing. Limit: 20 requests/min, and 50 requests/day until you have ever bought USD 10 of credits (then 1,000/day). Free model list changes; browse <https://openrouter.ai/models?q=free>. |
| Groq | <https://console.groq.com/keys> | `GROQ_API_KEY` | Free tier, no card; fast; limits are per model, check the console. |
| Google Gemini | <https://aistudio.google.com/apikey> | `GEMINI_API_KEY` | Free tier through the OpenAI-compatible endpoint; limits vary by model. |

```powershell
$env:OPENROUTER_API_KEY = "sk-or-..."
python scripts/cloud_smoke.py --provider openrouter --model "<a :free model id>"
```

Free tiers may log or train on prompts, so use synthetic text only. They are
fine for wiring and adapter tests but not for the price/quality pilot, which
needs real paid prices. Do not paste the key anywhere that is committed.

## Run the whole app on a laptop (no GPU, no keys)

`FAKE_PROVIDERS=true` makes every model (local and cloud) a deterministic fake, so you can use the
full UI and every routing feature without Ollama or an API key. Nothing leaves the machine.

```powershell
python -m pip install -e ".[dev]"
$env:FAKE_PROVIDERS = "true"
$env:KEY_VAULT_MASTER_KEY = python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"
$env:JWT_SECRET = python -c "import secrets;print(secrets.token_urlsafe(48))"
python scripts/seed_demo.py                      # local-demo, cloud-cheap-demo, cloud-strong-demo
python -m uvicorn app.main:app --app-dir backend --port 8000
```

Frontend (Node 22+; verified with Node 26 / npm 11):

```powershell
cd frontend
npm install
npm run dev                                       # http://localhost:3000
```

Register (the first account becomes admin), then: Settings → Keys (any 8+ character fake key),
Settings → Models (choose the two demo cloud models), then Chat. Docker alternative:
`docker compose up --build` (add `--profile local-llm` to also start Ollama).

## Test with a real cloud key (when you have one)

1. Stop using fake providers: unset `FAKE_PROVIDERS` (or set it to `false`) and restart the backend.
2. Admin → Registry → *Add a model*: kind `cloud`, provider `openrouter`, endpoint
   `https://openrouter.ai/api/v1`, **Provider model id** = the OpenRouter id (e.g. a `:free` model),
   then *Set price* (use `0`/`0` for free models, or the real $/M tokens). Register two cloud
   models (a cheap and a strong one; free ones are fine for wiring tests).
3. Settings → Keys: paste the key, press **Test**. Status must become `ok` (a failed status means
   the key or base URL is wrong; the test sends no user content).
4. Settings → Models: choose cheap + strong. Chat → tick *Allow cloud models* and ask a question.
   The route panel shows the chosen model, estimated vs measured cost/tokens/latency.
5. Free tiers may log prompts: use synthetic text only.

`scripts/cloud_smoke.py` does the same connectivity check from the command line.

## End-to-end browser test (Playwright)

With the backend running as above (`FAKE_PROVIDERS=true`, `seed_demo.py`, a **fresh database** so the
first registered user is admin) and the frontend on :3000:

```powershell
cd frontend
npx playwright install chromium
npm run e2e
```

The specs are `frontend/e2e/flow.spec.js` (register → add key → choose models → upload → ask →
route explanation → admin disables the local model → blocked/consent dialog → feedback → analytics)
and `a11y.spec.js` (axe WCAG A/AA scan). Both passed against the fake-provider stack. Run `npm run build`
and `npm start` first (the tests hit the production build on :3000). The first registered account must be
the test user, so start from a fresh database.

## Evaluation harness

`python -m eval.run_all` builds a synthetic dataset, runs the oracle, calibrates, trains the frozen
router, runs all five policies on the test split (3 seeds), a latency-shift stream, the privacy
evaluation, ablations and error analysis, and writes `eval/reports/<run_id>/report.{json,md}`.
With the default `--executor sim` every report is labelled **SIMULATED**: it checks the pipeline,
it is not a result. Individual steps: `make eval-build eval-oracle eval-calibrate eval-train-frozen
eval-static eval-privacy`; quick check: `make eval-smoke`.

Live runs need (in this order): the Phase 0 pilots, real model IDs/prices in `configs/models.yaml`,
`EVAL_API_KEY` (the admin evaluation key, USD 100 cap), then
`python -m eval.run_all --executor live`. Results are cached by (item, model, prompt hash, config
hash) so reruns cost USD 0, and calls hard-stop at the cap. The plan to freeze before the final test
is in `docs/eval-plan.md`.

## Database and migrations

`alembic upgrade head` applies `0001_initial` and `0002_phase5_8` (consent/model/routing columns and
feedback, scored-outcome, rating, ledger, privacy-finding and eval tables). `alembic check` must
report no drift (CI enforces it). The API also calls `create_all` at startup for the demo; on
PostgreSQL prefer running migrations.

### Phase 5–11 additions

New environment variables: `FAKE_PROVIDERS`, `CHAT_RATE_PER_MIN` (default 30), `UPLOAD_RATE_PER_MIN`
(20), `PROVIDER_TIMEOUT_S` (60), `CONFIG_DIR` (where `configs/*.yaml` live; set in Docker).
New dependencies: `numpy`, `pyyaml`, `httpx` (runtime), `import-linter` (dev). New commands:
`lint-imports`, `make seed`, `make retention`, `make eval-*`.

## Updating this guide

At the end of each phase, update:

1. Current status.
2. Prerequisites and environment variables.
3. Setup, migration, and validation commands.
4. Service URLs or ports.
5. Deferred checks and machine-specific requirements.
