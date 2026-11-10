# 04 — Frontend spec (Next.js App Router)

| Route | Role | Content |
|---|---|---|
| `/login`, `/register` | public | forms, error states, lockout message |
| `/chat` | user | session sidebar; mode toggle (Local-only / Cloud-allowed); doc upload + label chip (public/internal/confidential); cost preference slider (lowest · balanced · best quality); message stream; **Route panel** per answer |
| `/settings/keys` | user | add/test/delete provider connection (OpenRouter default or custom base URL); masked `…last4`; monthly cap; status |
| `/settings/models` | user | choose cheap + strong cloud model from connection's list; shows price snapshot date; local model status |
| `/settings/privacy` | user | default mode, retention (session-only vs opt-in persistence), delete-all-data, consents list/revoke |
| `/analytics` | user/admin | cost, latency, local-share, quality by task/model (Recharts); estimated vs observed in separate series |
| `/rate` | rater | blind queue: prompt + evidence + response, no model name; 4 sliders 1–5 |
| `/admin` | admin | registry + prices, institutional policy, policies/versions + rollback, budgets, users |

## Route panel (every response)
Chosen model · rule ID or policy+version · eligible set and **removed models with reasons** · est. vs observed tokens/cost/latency (separate columns) · status · compression notice · source references (chunk/page) · fallback/retry trail · "why blocked" for abstain.

## UX rules
Privacy state always visible in the chat header. Cloud-blocked ≠ error: show constraint + fix. Consent dialog names destination model and shows a payload preview (redacted view) before approval. Keys never shown after save. Session-expiry banner (60-min inactivity). Accessible (labels, focus, contrast), responsive.
