# 08 — Open questions, assumptions, and suggested improvements

## Assumptions made (change if wrong)
1. Local accounts + admin/user/rater roles; users bring their own OpenRouter (or OpenAI-compatible) key. Evaluation uses an admin lab key under the USD 100 cap.
2. Hardware: 16 GB RAM + ~8 GB VRAM → 7–8B 4-bit local model via Ollama; exact model chosen in Phase 0 by profiling.
3. Two cloud options = one cheap + one strong model, both via one OpenRouter adapter.
4. English, digital PDF/TXT only.

## Open questions for the team (answer in PROGRESS.md decision log)
- Which exact cloud model IDs (cheap/strong) after the price pilot?

Resolved:
- Raters do not require departmental approval before Phase 7 rating collection.
- Open self-registration is allowed for the lab demo.
- Opt-in persistent history ships in the MVP.

## Suggested tweaks (recommended, ordered by value)
1. **Shadow mode for the bandit.** Before it serves traffic, run it alongside fixed rules and log what it *would* pick. Gives free safety evidence and extra data for off-policy evaluation.
2. **Use the logged propensities.** You already log P(action). Add inverse-propensity / doubly-robust off-policy estimates next to the oracle-subset regret; it strengthens RQ2 without extra API spend.
3. **Cache aggressively in eval.** Key = (item, model, prompt hash, config hash). Protects the USD 100 budget and makes reruns free.
4. **BYOK cost guard.** Because users' own money is involved, show estimated cost before send for cloud routes and enforce per-connection caps (already in Phase 1/2).
5. **LLM-as-judge only on non-sensitive items,** with a fixed judge model and frozen prompt, and validate it against your human ratings before using it as the automatic score `A`.
6. **PDF parser licence.** PyMuPDF is AGPL; default to `pypdf` (+ `pdfminer.six` fallback) unless the licence is acceptable.
7. **Timeline reality check (today is 9 Nov 2026).** The December baseline demo needs Phases 0–5 plus a minimal chat UI. Run Phase 6 (full UI), 7 (analytics/rating) and 8 in parallel by owner; see phase files for the minimal-December cut.
8. **Add a "provider drift" canary.** A small fixed set of prompts re-run weekly to detect price/latency/quality changes; supports the proposal's "rerun comparisons when providers change".
9. **Optional stretch, not core:** LinUCB or Thompson sampling as the second bandit (proposal lists it as stretch) — add only after Phase 10 is complete.
10. **Local embeddings later.** BM25 is the MVP retrieval (proposal-aligned). A local embedding retriever is a clean ablation, not a dependency.

## Implementation notes added during the build
- Shadow mode, propensity logging with IPS/DR, evaluation caching and the PDF-parser choice
  (pypdf) from the suggestions above are implemented.
- Still open for the team: LLM-as-judge for the automatic score (not implemented), per-IP auth rate
  limits, dependency audit and lockfiles, Presidio/spaCy detector upgrade, and the exact cloud model
  IDs after the pricing pilot.
- Consent is keyed by model **slug** (not a database id) and by the exact serialised payload hash.
