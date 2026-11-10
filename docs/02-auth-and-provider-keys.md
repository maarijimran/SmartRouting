# 02 — Login, roles, and connecting GPT / Claude (BYOK)

## Decision
Local accounts + role-based access. Users sign in to SmartRoute, then **connect their own provider key(s)**. Default provider is **OpenRouter** (one key reaches GPT, Claude and others through an OpenAI-compatible API). A custom OpenAI-compatible `base_url` + key is also allowed. Keys are stored server-side, encrypted (proposal NFR: server-side API keys).

## Accounts
- Register (email + password; admin can disable open registration for the lab demo), login, logout, refresh, change password.
- Passwords: argon2id via argon2-cffi. Min length 10. Lockout/backoff after 5 failed attempts per account+IP.
- Access token JWT (15 min, in memory on the client); refresh token (7 days, opaque, hashed in DB, httpOnly + Secure + SameSite=Strict cookie, rotated on use, revocable).
- CORS locked to the frontend origin; CSRF token on cookie-auth endpoints (refresh/logout).
- First registered user (or `ADMIN_EMAIL` env) becomes admin; seed script creates demo admin/user/rater.

## Roles
| Role | Can |
|---|---|
| user | chat, upload, set privacy mode/doc labels, manage own keys + enabled models, view own metrics, give feedback, delete own data |
| rater | everything a user can + blind-rating queue (model identity hidden) |
| admin | registry (models, prices, context limits), institutional policy (can force local-only/deny cloud), global budget caps, policy versions + rollback, user management, run exports |

## Provider connections (BYOK) — `keys/`
Fields: `provider` (openrouter | openai_compat), `base_url`, `label`, encrypted key, `last4`, `status`, `monthly_budget_usd`, `created_at`.
Flow:
1. User pastes key in Settings → Keys. Frontend sends once over HTTPS; never stored client-side.
2. Backend encrypts with AES-256-GCM (random nonce per key; master key from env `KEY_VAULT_MASTER_KEY`, 32 bytes base64; supports key rotation via `key_version`).
3. "Test connection": backend calls the provider's model-list/auth endpoint and stores status + discovered models. The test call goes through `egress.send()` with a fixed non-user payload.
4. User chooses **two cloud models** from the connection's list (one cheap, one strong) → `user_model_prefs`. Prices are pulled/entered into the registry with a timestamp; unknown price ⇒ not eligible.
5. API returns only `{id, provider, label, last4, status}`. Delete = hard delete ciphertext.
Decrypt happens only inside `gateway/egress.py` right before the HTTP call; plaintext is never assigned to a loggable object.

## Budget and cost safety with BYOK
- Per-connection monthly cap and per-session cap set by the user; admin global cap for the evaluation key (USD 100 plan: 15 pilot / 55 benchmark / 15 adaptive / 15 contingency).
- `budget.py` reserves estimated cost before dispatch, settles with measured cost after; refuses when `spent + estimate > cap`.
- Evaluation runs use an **admin-owned lab key** (`purpose='eval'`), never users' keys.

## Consent (privacy-related)
Cloud-allowed + sensitive/confidential content requires consent scoped to {destination(provider+model), payload hash, expiry}. Stored in `consents`; the routing event references `consent_id`. Institutional prohibition (admin policy) overrides user consent. See 05-privacy-and-routing-spec.md.

## Threat-model notes (state in report)
In scope: routing mistakes, key leakage via API/logs, cross-user access, replayed consent. Out of scope: compromised host, general prompt-injection detection. Test: user A cannot read user B's sessions, keys, documents, feedback.