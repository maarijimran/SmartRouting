"""Transformer PII detector: piiranha-v1 (mDeBERTa-v3 token classification), run locally.

The model never leaves the host. Text is split into overlapping 256-token windows, every
token gets its most likely label, and adjacent tokens of the same entity type are merged into
character spans. It runs alongside the regex patterns (which cover Pakistani formats the model
was not trained on: CNIC, 03xx phones, student IDs, PK IBAN).

Any failure (missing model, CUDA error, tokenizer error) raises, so ``PrivacyScanner`` reports
a scanner error and cloud models are removed: fail closed (CLAUDE.md invariant 3).

Model licence: CC-BY-NC-ND-4.0 (non-commercial, no derivatives). Used unmodified for the FYP.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections import OrderedDict
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from app.privacy.patterns import PatternFinding, find_pattern_entities

log = logging.getLogger("smartroute.privacy.ner")

# piiranha labels -> SmartRoute entity types (stored as type + count only, never text)
LABEL_TO_TYPE: dict[str, str] = {
    "I-GIVENNAME": "person_name",
    "I-SURNAME": "person_name",
    "I-EMAIL": "email",
    "I-TELEPHONENUM": "phone",
    "I-CREDITCARDNUMBER": "card",
    "I-ACCOUNTNUM": "account_number",
    "I-IDCARDNUM": "id_number",
    "I-SOCIALNUM": "id_number",
    "I-DRIVERLICENSENUM": "id_number",
    "I-TAXNUM": "id_number",
    "I-STREET": "address",
    "I-BUILDINGNUM": "address",
    "I-CITY": "address",
    "I-ZIPCODE": "address",
    "I-DATEOFBIRTH": "date_of_birth",
    "I-PASSWORD": "password",
    "I-USERNAME": "username",
}
WINDOW = 256  # model context, including [CLS] and [SEP]
OVERLAP = 64  # tokens shared by consecutive windows so entities on a boundary are not cut


def merge_token_predictions(
    text: str,
    offsets: Sequence[tuple[int, int]],
    labels: Sequence[str],
    scores: Sequence[float],
    *,
    threshold: float = 0.5,
    ignore: Iterable[str] = (),
) -> list[PatternFinding]:
    """Merge per-token labels into entity spans (pure function; unit tested without a model).

    Adjacent tokens with the same entity type, separated only by whitespace, form one span
    (so "Ayesha Khan" is one ``person_name``). A span is kept when the mean token
    probability reaches ``threshold``.
    """
    ignored = set(ignore)
    spans: list[PatternFinding] = []
    current: list | None = None  # [type, start, end, scores]

    def close() -> None:
        nonlocal current
        if current is not None:
            kind, start, end, values = current
            while start < end and text[start].isspace():
                start += 1
            while end > start and text[end - 1].isspace():
                end -= 1
            score = sum(values) / len(values)
            if end > start and score >= threshold:
                spans.append(PatternFinding(kind, start, end, round(score, 4)))
        current = None

    for (start, end), label, score in zip(offsets, labels, scores, strict=True):
        kind = LABEL_TO_TYPE.get(label)
        if kind in ignored:
            kind = None
        if kind is None or start == end:
            if kind is None:
                close()
            continue
        if current is not None and current[0] == kind and not text[current[2] : start].strip():
            current[2] = end
            current[3].append(score)
            continue
        close()
        current = [kind, start, end, [score]]
    close()
    return spans


def window_starts(n_tokens: int, body: int = WINDOW - 2, overlap: int = OVERLAP) -> list[int]:
    """Start index of each window so that every token is covered at least once."""
    step = max(1, body - overlap)
    starts = [0]
    while starts[-1] + body < n_tokens:
        starts.append(starts[-1] + step)
    return starts


class PiiModelDetector:
    """Lazy-loaded, thread-safe, cached piiranha inference. ``__call__(text) -> findings``."""

    version = "piiranha-v1"

    def __init__(
        self,
        model_path: str,
        *,
        threshold: float = 0.5,
        ignore: Iterable[str] = (),
        device: str = "auto",
        batch_size: int = 16,
        cache_size: int = 1024,
    ) -> None:
        self.model_path = model_path
        self.threshold = threshold
        self.ignore = frozenset(ignore)
        self.device_pref = device
        self.batch_size = batch_size
        self.cache_size = cache_size
        self._lock = threading.Lock()
        self._model = None
        self._tokenizer = None
        self._device = "cpu"
        self._id2label: dict[int, str] = {}
        self._cache: OrderedDict[str, tuple[PatternFinding, ...]] = OrderedDict()

    @property
    def device(self) -> str:
        return self._device

    def warm_up(self) -> None:
        """Load the model and run one tiny inference (call at startup)."""
        self("warm up")

    def _load(self) -> None:
        import torch
        from transformers import AutoModelForTokenClassification, AutoTokenizer

        path = Path(self.model_path)
        if not self.model_path or not (path / "config.json").exists():
            raise FileNotFoundError(f"PII model not found at {self.model_path!r} (PII_MODEL_PATH)")
        device = self.device_pref
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        tokenizer = AutoTokenizer.from_pretrained(path, use_fast=True)
        model = AutoModelForTokenClassification.from_pretrained(path, use_safetensors=True)
        if device.startswith("cuda"):
            model = model.half()
        model.to(device).eval()
        self._tokenizer, self._model, self._device = tokenizer, model, device
        self._id2label = {int(k): v for k, v in model.config.id2label.items()}
        log.info("loaded PII model from %s on %s", path, device)

    def __call__(self, text: str) -> list[PatternFinding]:
        if not text or not text.strip():
            return []
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return list(hit)
            if self._model is None:
                self._load()
            findings = tuple(self._detect(text))
            self._cache[key] = findings
            if len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        return list(findings)

    def _detect(self, text: str) -> list[PatternFinding]:
        import torch

        tok = self._tokenizer
        encoded = tok(text, add_special_tokens=False, return_offsets_mapping=True)
        ids: list[int] = encoded["input_ids"]
        offsets: list[tuple[int, int]] = [tuple(o) for o in encoded["offset_mapping"]]
        if not ids:
            return []
        body = WINDOW - 2
        best_label = [len(self._id2label) - 1] * len(ids)
        best_prob = [-1.0] * len(ids)
        starts = window_starts(len(ids), body)
        for b in range(0, len(starts), self.batch_size):
            batch = starts[b : b + self.batch_size]
            rows = [[tok.cls_token_id, *ids[s : s + body], tok.sep_token_id] for s in batch]
            width = max(len(r) for r in rows)
            input_ids = torch.full((len(rows), width), tok.pad_token_id, dtype=torch.long)
            mask = torch.zeros((len(rows), width), dtype=torch.long)
            for i, row in enumerate(rows):
                input_ids[i, : len(row)] = torch.tensor(row)
                mask[i, : len(row)] = 1
            with torch.inference_mode():
                logits = self._model(
                    input_ids=input_ids.to(self._device), attention_mask=mask.to(self._device)
                ).logits
            probs, labels = logits.float().softmax(-1).max(-1)
            probs, labels = probs.cpu().tolist(), labels.cpu().tolist()
            for i, start in enumerate(batch):
                for j in range(1, len(rows[i]) - 1):  # skip [CLS]/[SEP]
                    token = start + j - 1
                    if probs[i][j] > best_prob[token]:
                        best_prob[token], best_label[token] = probs[i][j], labels[i][j]
        return merge_token_predictions(
            text,
            offsets,
            [self._id2label[label] for label in best_label],
            best_prob,
            threshold=self.threshold,
            ignore=self.ignore,
        )


def _overlaps(a: PatternFinding, b: PatternFinding) -> bool:
    return a.start < b.end and b.start < a.end


class HybridDetector:
    """Regex patterns + transformer NER. Regex wins where both fire on the same span."""

    def __init__(
        self,
        model: Callable[[str], list[PatternFinding]],
        patterns: Callable[[str], list[PatternFinding]] = find_pattern_entities,
    ) -> None:
        self.model = model
        self.patterns = patterns

    def warm_up(self) -> None:
        warm = getattr(self.model, "warm_up", None)
        if warm is not None:
            warm()

    def __call__(self, text: str) -> list[PatternFinding]:
        regex = self.patterns(text)
        learned = [m for m in self.model(text) if not any(_overlaps(m, r) for r in regex)]
        return regex + learned
