# FYP1 baseline demo script

Setup: follow SETUP.md "Run the whole app on a laptop" (fake providers) for a rehearsal, then
repeat on the GPU machine with real Ollama and an OpenRouter key for the real demo. Start from a
fresh database so the first registered account is the admin.

## Rehearsal path (fake providers, ~10 minutes)
1. **Register** an admin account. Settings → Keys → add any 8+ char key (fake mode accepts it) →
   **Test** shows `ok`. Settings → Models → choose `cloud-cheap-demo` and `cloud-strong-demo`.
2. **Local-only (default).** Chat → New session → upload a short TXT/PDF → ask a question. Show the
   header (🔒 Local-only), the route panel (`local-demo`, rule `label_forbids_cloud`, cloud models
   removed with reason *Local-only mode*), estimated vs measured columns.
3. **Cloud allowed, public document.** Tick *Allow cloud models*, ask a cross-section question →
   routed to the strong model (rule `distributed_evidence_strong`) and a simple question → cheap
   model. Show the eligible/removed lists and the cost columns.
4. **Confidential content.** Set the session label to `confidential` with cloud allowed: while a
   local model is healthy the request routes locally and both cloud models are listed as removed
   (*Consent required*). To show the block and consent flow, take the local model away (Admin →
   Registry → untick it, or stop Ollama) and ask again → *Blocked — no eligible model* with the
   constraint and fix. Open *Review & consent*, show the redacted preview naming the destination
   model, grant it → the identical request now routes. Revoke it under Settings → Privacy.
5. **PII in the prompt** (synthetic, e.g. `student42@example.test`) → same consent path; show that
   the preview masks it and the analytics privacy counters record type+count only.
6. **Abstain:** remove the keys (or switch to a session with only unusable models) → actionable
   explanation (`No provider key`, `Over budget`, …).
7. **Fallback:** (real run) stop Ollama mid-demo → local is removed (`Host unreachable`); cloud
   still works only if eligible. A local-only request is never retried on cloud.
8. **Feedback + analytics:** rate an answer, open Analytics (estimated vs measured series, local
   share, p50/p95, routing overhead vs 500 ms target).
9. **Admin:** Policies tab — fixed rules v0 active; *Learn from fresh outcomes now* publishes a
   shadow version; show *Roll back*. Registry tab — price snapshots.

## Real-provider validation checklist (needs the GPU machine and keys)
- [ ] One Ollama model enabled; local-only never reaches the cloud (check the egress block counter).
- [ ] Two cloud models with real model IDs and dated price snapshots; connection **Test** is `ok`.
- [ ] Document QA and summary prompts run; selected model, rule, estimated vs measured
      tokens/cost, latency, retry behaviour and abstention reasons recorded.
- [ ] Routing overhead recorded against the 500 ms target (`perf-latest.json` from the test suite,
      plus per-event `routing_latency_ms`).
- [ ] `docs/pilot-hardware.md` written from `docs/pilot-hardware.json`; `docs/stack-freeze.md`
      updated with the chosen model IDs.
