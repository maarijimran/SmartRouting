# 03 — Data model and API contract

## PostgreSQL tables (SQLAlchemy + Alembic). All `id` = UUID, timestamps UTC.
**Identity**: `users(id, email uniq, password_hash, role, is_active, created_at)` · `refresh_tokens(id, user_id, token_hash, expires_at, revoked_at, rotated_from)`
**Providers**: `provider_connections(id, user_id|null, purpose[user|eval], provider, base_url, label, key_ciphertext, key_nonce, key_version, last4, status, monthly_budget_usd, created_at)`
**Registry**: `models(id, slug, kind[local|cloud], provider, endpoint, context_limit, max_output, tokenizer, quant, min_ram_gb, min_vram_gb, enabled)` · `model_prices(model_id, input_per_mtok, output_per_mtok, captured_at, source)` · `model_health(model_id, ts, ok, p50_ms, err_rate)` · `user_model_prefs(user_id, model_id, connection_id, enabled, tier[cheap|strong])`
**Policy**: `institutional_policy(id, allow_cloud, forbid_labels[], updated_by, updated_at)` · `policy_versions(id, name, kind[rules|frozen|bandit], params_json, parent_id, epsilon, created_at, is_active)`
**Content (expires)**: `chat_sessions(id, user_id, mode[local_only|cloud_allowed], label, persist_opt_in, last_active_at, expires_at)` · `documents(id, session_id, filename, label, pages, bytes, text_encrypted?, created_at)` · `chunks(id, document_id, idx, text, tokens, label)` · `messages(id, session_id, role, content, label, tokens, created_at)`
 → raw content purged after 60 min inactivity unless `persist_opt_in`; deletion endpoint wipes immediately.
**Privacy**: `privacy_findings(id, event_id, scope[prompt|chunk|history|payload], entity_type, count, detector_version)` (no text) · `consents(id, user_id, session_id, destination_model_id, payload_hash, granted_at, expires_at, revoked_at)`
**Routing (metadata, kept 30 days)**: `routing_events(id, user_id, session_id, ts, task_type, features_json, eligible_json, removed_json[{model,reason}], chosen_model, action_prob, policy_version_id, rule_id, est_in_tokens, est_out_tokens, est_cost, est_latency_ms, abstained, abstain_reason, consent_id)` · `attempts(id, event_id, attempt_no, model_id, status[ok|fail|timeout|empty|truncated|blocked], in_tokens, out_tokens, cost_usd, ttft_ms, latency_ms, error_class)`
**Feedback**: `feedback(id, event_id, rater_id, source[user|rater|auto], correctness, relevance, completeness, usefulness, auto_score, blind bool, created_at)` · `scored_outcomes(event_id, attempt_id, quality, q_source, reward, cost, latency, usable_for_update bool)`
**Budget**: `budget_ledger(id, connection_id, event_id, kind[reserve|settle], usd, ts)`
**Eval**: `eval_runs(id, name, git_sha, config_hash, seed, started_at, notes)` · `eval_items(id, run_id, item_id, doc_id, split, policy, model, outputs_ref, metrics_json)`

## REST API (`/api/v1`, JSON; SSE for generation)
Auth: `POST /auth/register|login|refresh|logout` · `GET /me` · `POST /me/password`
Keys: `GET/POST /connections` · `POST /connections/{id}/test` · `DELETE /connections/{id}` · `PUT /me/models` (choose cheap/strong)
Registry (admin write): `GET /models` · `PUT /models/{id}` · `PUT /models/{id}/price` · `GET /models/health`
Sessions/docs: `POST /sessions` · `PATCH /sessions/{id}` (mode, label) · `DELETE /sessions/{id}` · `POST /sessions/{id}/documents` (multipart) · `PATCH /documents/{id}` (label) · `DELETE /documents/{id}`
Chat: `POST /sessions/{id}/chat` → SSE events: `route` (decision, eligible, removed, explanation), `token`, `compression_notice`, `done` (measured metrics), `abstain`, `error`
Consent: `POST /consents` (scoped) · `DELETE /consents/{id}`
Feedback: `POST /events/{id}/feedback` · rater: `GET /rater/queue` (model hidden) · `POST /rater/{item}/rating`
Analytics: `GET /analytics/summary|by-model|by-task|cost-latency|privacy` (user-scoped; admin sees global)
Admin: `GET/POST /policies` · `POST /policies/{id}/activate` · `POST /policies/rollback` · `GET/PUT /institutional-policy` · `POST /export/eval`
Standard errors: `{code, message, constraint?, removed_models?}`. Unsupported/unreadable files → 422 with reason.
