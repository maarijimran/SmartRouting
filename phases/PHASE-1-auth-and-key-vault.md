# PHASE 1 — Auth, roles, provider-key vault (BYOK)
**Goal:** users can register/login and securely connect their GPT/Claude access (via OpenRouter or OpenAI-compatible endpoint).
**Prereqs:** Phase 0. **Read:** docs/02, docs/03 (identity + providers), docs/04 (login + keys pages).

## Tasks
- [ ] Models + migrations: `users`, `refresh_tokens`, `provider_connections`, `user_model_prefs`, `budget_ledger`.
- [ ] `core/security.py`: argon2id hashing, JWT (15 min), refresh rotation, lockout/backoff.
- [ ] `auth/`: register, login, refresh, logout, `/me`, change password; `require_role()` dependency; seed script (admin/user/rater).
- [ ] `core/crypto.py` + `keys/vault.py`: AES-256-GCM encrypt/decrypt with versioned master key; `decrypt` importable only from `gateway/egress.py` (linter rule).
- [ ] `keys/router.py`: create/list/test/delete connection; masked output only; connection test via a stub egress for now (real call lands in Phase 2).
- [ ] Frontend: `/login`, `/register`, `/settings/keys`, auth context with in-memory access token + cookie refresh.
- [ ] Per-connection monthly cap fields (enforced in Phase 2).

## Acceptance (tests)
Wrong password/lockout · refresh rotation & revocation · role guards (user cannot hit admin routes) · user A cannot list/delete user B's connection · API/log canary: a seeded key string never appears in any response or log · ciphertext differs per save (nonce) · key rotation re-encrypt script works.
**Out of scope:** model calls, SSO.
