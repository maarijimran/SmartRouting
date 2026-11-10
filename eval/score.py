"""Automatic scorers as an importable library (implementation lives in the backend package)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.feedback.scoring import (  # noqa: E402,F401
    automatic_score,
    best_f1,
    evidence_overlap,
    exact_match,
    normalize,
    rubric_coverage,
    token_f1,
)
