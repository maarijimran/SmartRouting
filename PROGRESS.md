# PROGRESS (updated at the end of every phase; statuses are deliberately conservative)

Legend: DONE = acceptance items that can be checked without outside resources pass in `make test`.
"Needs X" lists what only the team can supply. Nothing below claims a measured result.

| Phase | Name | Owner | Status | Notes |
|---|---|---|---|---|
| 0 | Bootstrap + hardware & pricing pilot | A1 | IN-PROGRESS | Skeleton, CI, compose (Ollama optional profile), migrations, scrubbing logger, import-linter all done. **Hardware pilot run** on an RTX 4000 Ada (20 GB): qwen2.5 7B, llama3.1 8B and llama3.2 3B (q4_K_M) all fit fully on GPU at 8k context (`docs/pilot-hardware.json`). Pending: choosing the local model, the paid pricing pilot, real cloud model IDs/prices. Free OpenRouter models are used for wiring tests only. |
| 1 | Auth, roles, key vault (BYOK) | A2 / T2 | DONE | Argon2id, JWT + rotating refresh, lockout, roles, AES-GCM vault, masked keys, real connection test (probe sends no user content). |
| 2 | Registry, adapters, health, budgets, retries | A2 | DONE | Registry + prices + health, fake/Ollama/OpenAI-compat adapters, budget hard stop (per-connection monthly ledger), single egress. Real Ollama smoke test still needs the GPU machine. |
| 3 | Documents, retrieval, context | T1 | DONE | PDF/TXT limits, page-aware chunks, BM25, local history compression + notice, retention purge. |
| 4 | Privacy layer + outbound gate | T2 | DONE | Fail-closed gate, scoped consent, institutional policy, egress re-scan of the final payload, CI privacy gate. Detector = regex + optional local piiranha-v1 transformer (`PII_DETECTOR=piiranha`; names, addresses, account/ID numbers, passwords). Sensitive turns now stop for a **user review** (findings + redacted preview → answer locally or consent to one cloud model). |
| 5 | Rule router + end-to-end pipeline | A3 | IN-PROGRESS | Complete and tested end to end on fake providers (route/token/compression_notice/done/abstain/error SSE, retries re-enter eligibility, no mid-stream switch, persisted events/attempts/findings/ledger). **Manual run on real local + 2 cloud models pending** (needs Ollama machine + an OpenRouter key). |
| 6 | Frontend | T1 | DONE (fake providers) | `npm run build` succeeds (Next 15, 13 routes) and the Playwright flow (register → key → models → upload → ask → route panel → admin disables local → blocked + consent dialog → feedback → analytics) **passes against the real backend with `FAKE_PROVIDERS=true`**. An axe WCAG A/AA scan reports no violations on the pages a normal user can reach (`/rate` and `/admin` redirect non-privileged users, so they were not scanned). Not done: Lighthouse score, a run against real providers, TypeScript client generation (the API client is hand-written). `npm audit` flags PostCSS inside `next` (build-time; fix needs Next 16, a breaking upgrade). |
| 7 | Logging, feedback, blind rating, analytics | T3 | DONE | Reward math with worked-example tests, scorers, feedback → scored outcomes (deferral, R=-1 failures, privacy exclusions), blind rater queue (leak test), κ + source-bias reports, analytics with hand-computed fixtures, CSV/JSON export, retention jobs. LLM-judge scorer not implemented (optional). Actual 120-item human rating still to be collected. |
| 8 | Dataset, eval harness, calibration | M1 / M2 | IN-PROGRESS | Builder (synthetic + QASPER-format loader), grouped 60/20/20 splits + leakage test, cached/budget-guarded executors, oracle, calibrate, frozen, replay, stats, report, `make eval-smoke`. **Pending:** real QASPER curation, live runs, real C_ref/L_ref (reward.yaml is provisional), human ratings, `docs/eval-plan.md` review by all members + supervisor, `eval-freeze-0` tag. |
| 9 | Bandit + frozen + training | M3 | DONE (code) | ε-greedy ridge over eligible set, probabilities logged, selected-action-only immutable updates every 50, cold-start handoff, shadow mode, rollback (admin + reward drop / error spike / privacy-gate red), cloud exploration off when privacy gate red. Property tests pass. Needs real scored data before it means anything. |
| 10 | Experiments, ablations, statistics | M4 | IN-PROGRESS | Static + stream experiments, privacy P/R and unauthorised dispatch, IPS/DR, ablations (reward weights, features, ε), clustered bootstrap CIs, error analysis all run on the **simulated** executor only. Real experiments need frozen eval + live runs. |
| 11 | Hardening, docs, release | A4 / T4 | IN-PROGRESS | Security headers, rate limits, isolation/injection/limit tests, perf test (routing overhead recorded), docs. Pending: dependency audit, lockfiles, clean-clone compose test, `v1.0.0` tag. |

## Decision log
- Open self-registration is allowed for the lab demo.
- Departmental approval is not required before Phase 7 rating collection.
- Opt-in persistent history ships in the MVP; session-only retention remains the default.
- Cheap and strong cloud model IDs remain pending the Phase 0 pricing pilot.
- Ollama runs on a separate GPU machine; the laptop uses `FAKE_PROVIDERS=true` (see SETUP.md).
- Consent is bound to (user, session, model slug, exact payload hash); an abstained turn leaves no history so a retry after consenting is byte-identical.
- Unknown cloud health is treated as healthy; a recorded failure expires after 5 minutes so recovered providers are retried. Local models are live-probed per request.
- Evaluation numbers from `--executor sim` are pipeline checks and are labelled SIMULATED in every report.
- The PII model scans prompts **and** documents. When cloud is allowed but needs consent (findings or a confidential/internal label), the turn stops before routing with a `review` SSE event; the user chooses `sensitive_choice=local` or grants scoped consent and sends `sensitive_choice=cloud`. The choice only narrows the eligible set; consent is still per model + payload hash. A review is not a routing event and leaves no history.

## Deviations from the original plan (all recorded, none hidden)
- `models.provider_model` column added (provider-side model id); migration `0002_phase5_8`.
- Policy `version` strings: `0` = fixed rules, `bandit-N` = learned versions.
- Reward references (`c_ref_usd`, `l_ref_ms`) are provisional defaults until the pricing pilot runs.
- Presidio + spaCy replaced by iiiorg/piiranha-v1 (local transformer, CC-BY-NC-ND) + regex; regex-only remains the CI default. Added a keyword-anchored passport recogniser (the model has no passport label).
- Fixed `eval/build_dataset.py::_luhn_card`: it produced numbers failing the Luhn checksum yet labelled them sensitive, which showed as 3 false "unauthorised dispatches" in the privacy eval. After the fix: recall 1.0, 0 unauthorised dispatches on the 40-case smoke set (both detectors). Regression test added.
