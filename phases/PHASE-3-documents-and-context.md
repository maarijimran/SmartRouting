# PHASE 3 — Documents, retrieval, context manager  (proposal T1/T2 start)
**Goal:** local, shared evidence pipeline used identically by every routing policy.
**Prereqs:** Phase 0 (can run parallel to 1–2). **Read:** docs/01 steps 4–7, docs/05 (context management).

## Tasks
- [ ] `documents/parse.py`: digital PDF (pypdf; pdfminer fallback) and TXT; reject scanned/empty-text PDFs with a clear 422; enforce 10 MB / 100 pages (configurable after profiling).
- [ ] `documents/chunk.py`: section-aware chunking with page refs; deterministic chunk IDs.
- [ ] `documents/retrieve.py`: BM25 (rank_bm25) top-k with scores + margin; returns evidence with source refs.
- [ ] Session/doc/message persistence with `expires_at` (60-min inactivity) + purge job + delete endpoints.
- [ ] `context/token_count.py` (per-model tokenizer, safety factor) and `context/builder.py` (provider-independent messages; reserve output + margin; per-model fit check).
- [ ] `context/compress.py`: local summarisation of old turns using the local model; emits compression notice; summary inherits label.
- [ ] Task-type classifier (rule-based): qa / summary / explain.

## Acceptance
Fixture PDFs/TXT (public or synthetic) parse correctly · corrupt/scanned → clear error · retrieval returns expected evidence on a small gold set · context fit math verified for local and cloud limits · purge removes raw content after expiry (time-travel test) · same evidence given same input regardless of policy.
