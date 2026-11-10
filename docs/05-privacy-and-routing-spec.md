# 05 — Privacy, eligibility, reward and bandit spec (implement literally)

## Labels and modes
- Session mode: `local_only` | `cloud_allowed`. Document label: `public` | `internal` | `confidential`. Derived content inherits the highest label of its sources.
- Institutional policy (admin) can set `allow_cloud=false` or forbid labels → overrides any consent.

## Cloud eligibility decision table (per candidate cloud model)
| Condition | Cloud eligible? |
|---|---|
| mode = local_only | NO (regardless of detector) |
| institutional prohibition | NO |
| scanner error / unknown label / uncertain permission | NO |
| label = confidential OR sensitive entities detected, no valid scoped consent | NO |
| …with valid consent for {this model, this payload hash, unexpired} | YES |
| connection missing / budget exceeded / price unknown / unhealthy / context infeasible | NO |
| otherwise | YES |
Local model eligibility: healthy, fits context (after reserve + margin), RAM/VRAM headroom OK.

## Detector (`privacy/detector.py`)
Presidio AnalyzerEngine + spaCy NER + custom recognisers: email, phone (PK mobile formats `03xx-xxxxxxx`, `+92…`), CNIC-like `\d{5}-\d{7}-\d`, person names, IBAN/credit-card-like (Luhn), student-ID-like (`\d{2}K-\d{4}`), selected financial IDs. Output = findings (type, span, score) held in memory only; DB stores type+count. Thresholds tuned on dev only. Limitations are documented: no implicit-confidentiality detection → labels and local-only remain essential.
Scan scopes: prompt, each chunk sent, history, summaries, retrieved evidence, **final serialized payload** (outbound gate).

## Outbound gate (`privacy/gate.py`, called only by `gateway/egress.py`)
Input: final bytes + destination + policy + consent. Re-scan; compare payload hash with consent; return PASS/BLOCK(reason). Independent of any learned score. A BLOCK is logged as `blocked`, not a model failure (no R penalty).

## Context management
`token_count.py` uses per-model tokenizer (tiktoken fallback with safety factor 1.1 for unknown). Fit rule: `input_tokens + reserved_output + margin <= context_limit`. Older turns summarised **locally**, with `compression_notice` in the SSE stream. Summaries inherit labels.

## Reward (`routing/reward.py`)
```
H = (mean(correctness,relevance,completeness,usefulness) - 1) / 4          # human, [0,1]
A = automatic task score in [0,1]    # QA: token-F1/EM + evidence overlap; summary: rubric coverage
Q = 0.7H + 0.3A if both ; the one available (record q_source) ; none → defer update
R = 0.5Q + 0.3(1 - min(C/C_ref,1)) + 0.2(1 - min(L/L_ref,1))     # success
R = -1                                                           # failed / empty / timeout / truncated
```
C = measured API cost (include retries + auxiliary calls, local = 0 API cost, report local compute separately); L = measured latency. `C_ref`, `L_ref` fixed from pilot (Phase 0/8) **before** final test; stored in `configs/reward.yaml`. Privacy blocks are excluded from learning.

## Bandit (`routing/bandit.py`)
- Per model a: ridge regression `r̂_a = θ_aᵀ φ(x)`; φ = standardised numerics (scaler fit on train only) + task one-hot + constant.
- φ features: task type (qa/summary/explain), est. input tokens, evidence tokens, est. output tokens, retrieval top score + margin, doc pages, history turns, privacy mode, cost preference, per-model recent latency EWMA + failure rate, local load.
- Selection over **eligible** set only: with prob 1-ε pick argmax r̂; else uniform over eligible. Log true action probability (`ε/|A|` + `(1-ε)` for the argmax).
- ε: 0.10 → 0.02 linearly over 1,000 scored decisions (configs/routing.yaml).
- Cold start: fixed rules serve until each model has ≈50 scored non-sensitive calibration examples.
- Update: after every batch of 50 scored outcomes, refit only the **selected** model's regressor on its own scored data (optionally sliding window W tuned on dev). Save as new immutable `policy_versions` row.
- Rollback triggers: admin button; or auto if window mean reward < rules baseline − δ, or any privacy incident, or error-rate spike → activate previous version / fixed rules.
- Exploration on cloud models only after Phase 4 privacy suite passes (CI gate).
