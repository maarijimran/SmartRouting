# User, admin and deployment guide

## For users
1. **Register / sign in.** Passwords need 10+ characters; five failed sign-ins lock the account for
   a growing delay.
2. **Add a provider key** (Settings → Keys). Use OpenRouter (default) or any OpenAI-compatible
   endpoint. The key is encrypted, only shown as `…last4`, and only decrypted at the instant a cloud
   request is sent. Set a monthly cap to hard-stop spending. Use **Test** to verify it.
3. **Choose models** (Settings → Models): one cheap and one strong cloud model.
4. **Chat.** The header always shows the privacy state. Start in *local-only* (default): no cloud
   model is ever considered. Tick *Allow cloud models* to let eligible cloud models compete.
   Label the session or each document `public`, `internal` or `confidential`; derived content
   (summaries, history, evidence) inherits the highest label.
5. **Read the route panel** under each answer: chosen model, the rule or policy that fired,
   eligible vs removed models with reasons, estimated vs measured tokens/cost/latency (separate
   columns), sources (page refs), retry trail and any local compression notice.
6. **Blocked is not an error.** If every model is ruled out you get the constraint and the fix. For
   consent-required blocks you can review a redacted preview and consent to *that exact payload*
   for *that model* for 60 minutes; revoke under Settings → Privacy.
7. **Rate answers** (optional) to help the system learn. Delete everything any time under
   Settings → Privacy → *Delete my data*. Session content is deleted after 60 minutes of inactivity
   unless you opt in to keeping history.

## For admins
- **Registry:** add models (`provider model id` is what the provider expects), record dated price
  snapshots, enable/disable. A cloud model with no price is never used.
- **Institutional policy:** prohibit cloud entirely or by label; overrides any consent.
- **Policies:** fixed rules (v0) always exist. Learned versions are published every 50 scored
  outcomes and run in *shadow* (their choice is logged, rules serve) until you **Activate** one.
  **Roll back** restores the parent version or fixed rules. Automatic rollback fires on reward
  drop, error spike or a red privacy suite.
- **Budgets, users and roles** (`user`, `rater`, `admin`), **rater workflow** (enqueue → assign to
  two raters → agreement/bias report), **retention** (content 60 min, metadata 30 days), CSV/JSON
  export of scrubbed event metadata (never text).

## Deployment
- **Single machine:** `docker compose up --build` (add `--profile local-llm` for Ollama in
  Compose). Set `JWT_SECRET`, `KEY_VAULT_MASTER_KEY` (base64 of 32 random bytes), `ADMIN_EMAIL`,
  `DATABASE_URL`, `OLLAMA_URL`, `FRONTEND_ORIGIN`, `NEXT_PUBLIC_API_URL` (build-time for the
  frontend). Serve behind HTTPS in any shared deployment (the refresh cookie is `Secure`).
- **Ollama on another host:** see SETUP.md; never expose port 11434 beyond the LAN.
- **Back up** the database and the master key *separately*; losing the master key makes stored
  provider keys unrecoverable (users re-enter them). Rotation: `keys.vault.rotate_provider_key`.
- Run `make retention` (or the admin button) on a schedule.
