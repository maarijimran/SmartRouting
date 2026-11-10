# PHASE 4 — Privacy layer + outbound gate  (proposal T2 · Nov–Dec 2026)  ★ GATE for cloud exploration
**Goal:** privacy is a hard restriction in selection, exploration, preprocessing and fallback.
**Prereqs:** Phases 2, 3. **Read:** docs/05 (labels, decision table, detector, gate), docs/07 (privacy suite).

## Tasks
- [ ] `privacy/patterns.py` custom recognisers (email, PK phones, CNIC-like, student-ID-like, card/IBAN-like with checksum, selected financial IDs).
- [ ] `privacy/detector.py`: Presidio + spaCy + custom; scopes prompt/chunks/history/summaries/evidence/payload; findings stored as type+count only; detector version recorded.
- [ ] `privacy/labels.py`: label algebra + propagation to derived content.
- [ ] `privacy/consent.py`: scoped consent (destination, payload hash, expiry, revocation); API + frontend dialog contract.
- [ ] `privacy/policy.py`: institutional policy (admin) + `eligibility_for_cloud(model, ctx) -> (bool, reason)` implementing the decision table exactly.
- [ ] `privacy/gate.py` and wire into `gateway/egress.py` (replace stub; remove startup guard bypass).
- [ ] Synthetic privacy suite generator (`eval/privacy_suite.py`): identifiers, benign lookalikes, history leakage, consent change, retry, scanner failure. Canary strings for egress spy.
- [ ] Threshold tuning on the dev part only; report precision/recall separately from unauthorized-dispatch count.

## Acceptance
All items in docs/07 "Privacy regression suite" pass in CI · zero canary leaks to fake sink in blocked scenarios · scanner exception ⇒ cloud blocked · local-only works with detector disabled · CI job `privacy-gate` is required for merge.
**Do not start Phase 9 exploration on cloud models until this is DONE.**
