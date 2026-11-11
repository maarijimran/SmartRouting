# Limitations, ethics and security checklist

## Limitations (state these in the report; do not claim guarantees)
- **Privacy detection = regex patterns + an optional local transformer** (`PII_DETECTOR=piiranha`:
  iiiorg/piiranha-v1, mDeBERTa-v3, 17 PII types, run on the local GPU). Regex covers email, PK
  phone, CNIC, student ID, IBAN, Luhn-valid cards and keyword-anchored passport numbers; the model
  adds names, addresses, account/ID numbers, passwords, usernames and dates of birth. It does not
  detect implicit confidentiality or paraphrased identifiers, so labels and local-only mode remain
  essential. Known false positives on academic text: cited author names (`Vaswani et al.`), places
  (`Karachi`) and some technical tokens (`BM25` → address). They never leak anything: the user
  sees the findings in a review step and chooses local or consented cloud. Detector misses and
  gate passes are reported separately. Model licence: CC-BY-NC-ND-4.0 (non-commercial, used
  unmodified).
- **Hardware dependence:** the local model, its context limit and latency depend on the target GPU;
  none of those numbers exist yet (pilots not run).
- **Small, English, digital-PDF/TXT academic data.** No OCR, multimodal or tool use.
- **Single-process limits:** the rate limiter and retention scheduling are in-process / manual.
- **Simulated evaluation:** `--executor sim` checks the pipeline only. Real conclusions need the
  live, frozen protocol in `docs/eval-plan.md`.
- **Quality signal is sparse and noisy:** user ratings are optional; automatic scores are cheap
  proxies; early bandit updates are deferred until enough signal exists.
- **Savings and privacy are hypotheses to test**, never guarantees.

## Ethics
Only public/licensed or synthetic documents in fixtures and evaluation; synthetic identifiers use
reserved domains and made-up digits. User keys are never used for evaluation (admin key under the
USD 100 cap). Raw content is retained for 60 minutes unless the user opts in; metadata 30 days;
users can delete their data immediately. Raters see no model identity.

## Security review checklist (status as of this commit)
| Item | Status |
|---|---|
| Passwords hashed (Argon2), lockout/backoff, refresh rotation + reuse rejection | done, tested |
| Provider keys AES-GCM encrypted, decrypted only in `gateway/egress.py`, masked everywhere, absent from logs | done, tested (canary) |
| Single egress; adapters importable only in `gateway/` (import-linter in CI) | done |
| Outbound re-scan of the final serialised payload; fail closed; consent bound to payload hash | done, tested |
| Cross-user isolation (sessions, documents, consents, events, feedback) | done, tested |
| Uploaded text cannot change policy/consent/credentials/destinations | done, tested |
| Upload size/page limits, corrupt files → 422 | done, tested |
| Security headers, `Cache-Control: no-store` on API, CORS limited to the frontend origin | done |
| Per-user rate limits on chat and upload | done (in-memory) |
| Auth/login rate limiting beyond account lockout (per-IP) | **not done** |
| HTTPS / HSTS | deployment concern (reverse proxy) — **not done here** |
| Dependency audit (`pip-audit`, `npm audit`), pinned lockfiles | **not done** |
| CSRF: bearer-token API; refresh cookie is `SameSite=Strict` | reviewed |
| Access token in `sessionStorage` (XSS exposure trade-off) | accepted for MVP, noted |
