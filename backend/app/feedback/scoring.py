"""Automatic scorers (importable library; also exposed as eval/score.py).

All scorers return values in [0, 1] and are deterministic and offline.
"""

import re
import string
from collections import Counter

_ARTICLES = re.compile(r"\b(a|an|the)\b")


def normalize(text: str) -> str:
    text = text.lower()
    text = "".join(ch for ch in text if ch not in set(string.punctuation))
    text = _ARTICLES.sub(" ", text)
    return " ".join(text.split())


def token_f1(prediction: str, reference: str) -> float:
    pred, ref = normalize(prediction).split(), normalize(reference).split()
    if not pred or not ref:
        return float(pred == ref)
    common = Counter(pred) & Counter(ref)
    overlap = sum(common.values())
    if overlap == 0:
        return 0.0
    precision, recall = overlap / len(pred), overlap / len(ref)
    return 2 * precision * recall / (precision + recall)


def exact_match(prediction: str, reference: str) -> float:
    return float(normalize(prediction) == normalize(reference))


def best_f1(prediction: str, references: list[str]) -> float:
    return max((token_f1(prediction, ref) for ref in references), default=0.0)


def evidence_overlap(answer: str, evidence: list[str]) -> float:
    """Share of the answer's content words that appear in the supplied evidence."""
    words = [w for w in normalize(answer).split() if len(w) > 3]
    if not words:
        return 0.0
    bag = set(normalize(" ".join(evidence)).split())
    return sum(1 for w in words if w in bag) / len(words)


def rubric_coverage(summary: str, key_points: list[str]) -> float:
    """Fraction of rubric key points whose content words are mostly present in the summary."""
    if not key_points:
        return 0.0
    summary_words = set(normalize(summary).split())
    covered = 0
    for point in key_points:
        words = [w for w in normalize(point).split() if len(w) > 3] or normalize(point).split()
        if words and sum(1 for w in words if w in summary_words) / len(words) >= 0.6:
            covered += 1
    return covered / len(key_points)


def automatic_score(
    task: str,
    answer: str,
    *,
    references: list[str] | None = None,
    evidence: list[str] | None = None,
    key_points: list[str] | None = None,
) -> float | None:
    """A in [0,1] for a task, or None when no reference material exists (defer)."""
    if task == "qa" and references:
        f1 = best_f1(answer, references)
        if evidence:
            return 0.8 * f1 + 0.2 * evidence_overlap(answer, evidence)
        return f1
    if task in {"summary", "explain"} and key_points:
        return rubric_coverage(answer, key_points)
    return None
