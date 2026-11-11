# Stack freeze

## Phase 0 status

The runnable bootstrap uses Python 3.11+ compatibility, FastAPI, Uvicorn,
Pydantic Settings, PostgreSQL 16, Ollama, and a Next.js App Router frontend.
The backend smoke test is available with `make test`.

The exact local model, cloud model IDs, prices, and reward reference values are
intentionally **not frozen** until the hardware and pricing pilots run on the
target machine with an explicitly supplied evaluation key.

## Phase 2 implementation note

The runtime has normalized adapter contracts, deterministic fake-provider
testing, Ollama and OpenAI-compatible HTTP wrappers, model health/pricing
checks, budget reservation/settlement, bounded retry re-entry, and a guarded
single-egress boundary. No test calls a real provider.

The registry, price snapshots, health observations, and user model preferences
are persisted through SQLAlchemy/Alembic. Provider streaming normalizes text
chunks and terminal usage; the real Ollama smoke test requires Ollama and the
target local model to be installed.

## Phase 1 implementation note

The backend now uses Argon2id-compatible password hashing through
`argon2-cffi`, HS256 JWT access tokens, and AES-256-GCM provider-key encryption
with a random 96-bit nonce per save. Database persistence and refresh-cookie routes are implemented with SQLAlchemy
and secure, rotated HTTP-only cookies. Alembic migrations, lockout/backoff,
password-change, and minimal frontend auth screens are included. Provider
connection testing is an explicit stub until Phase 2's egress adapter exists.

## Phase 5–11 implementation notes (what actually shipped vs the original stack)
- **PII detector:** `presidio-analyzer` + spaCy were replaced by the local transformer
  iiiorg/piiranha-v1 (`torch` + `transformers`, optional extra `.[pii]`, selected with
  `PII_DETECTOR=piiranha`) combined with the regex/Luhn recognisers. Regex-only stays the default
  for CI. ~12 ms per short text, ~54 ms per 1,800 words on an RTX 4000 Ada (fp16).
- **Not used / deferred:** `presidio-analyzer` and spaCy (see above);
  `tiktoken` (token counts use a whitespace estimate with a 1.1 safety factor for unknown
  tokenizers); scikit-learn / pandas (ridge is implemented in NumPy); Recharts (charts are inline
  SVG to avoid an unbuildable-here dependency); Tailwind (plain CSS).
- **Added:** `numpy`, `pyyaml`, `httpx` at runtime; `import-linter` (dev); `@playwright/test` (dev).
- Frontend is plain JavaScript (no TypeScript) on Next.js 15.5 / React 19; built and E2E-tested with
  Node 26 / npm 11. `package-lock.json` is committed.
- Model IDs, prices and `C_ref`/`L_ref` are still **not frozen** (pilots pending).
