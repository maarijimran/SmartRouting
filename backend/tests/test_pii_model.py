"""PII model detector (piiranha) integration. Synthetic identifiers only.

Pure logic (span merging, windowing, regex/model merging, fail-closed config) runs everywhere.
Real-model tests run only when the weights exist (PII_TEST_MODEL_PATH or the sibling
"Pii detection model" folder) and torch/transformers are installed.
"""

import importlib.util
import os
from pathlib import Path

import pytest
from app.core.config import get_settings
from app.privacy.detector import PrivacyScanner, default_scanner
from app.privacy.gate import check_outbound, redact
from app.privacy.ner import (
    HybridDetector,
    PiiModelDetector,
    merge_token_predictions,
    window_starts,
)
from app.privacy.patterns import PatternFinding

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = Path(os.environ.get("PII_TEST_MODEL_PATH", ROOT.parent / "Pii detection model"))
HAS_MODEL = (
    (MODEL_PATH / "config.json").exists()
    and importlib.util.find_spec("torch") is not None
    and importlib.util.find_spec("transformers") is not None
)
needs_model = pytest.mark.skipif(not HAS_MODEL, reason="PII model weights / torch not available")


# --- pure logic ---------------------------------------------------------------------------


def test_adjacent_name_tokens_merge_into_one_span() -> None:
    text = "Contact Ayesha Khan today"
    offsets = [(0, 7), (7, 14), (14, 19), (19, 25)]
    labels = ["O", "I-GIVENNAME", "I-SURNAME", "O"]
    spans = merge_token_predictions(text, offsets, labels, [0.99, 0.9, 0.8, 0.99])
    assert [(s.entity_type, text[s.start : s.end]) for s in spans] == [
        ("person_name", "Ayesha Khan")
    ]


def test_low_confidence_and_ignored_types_are_dropped() -> None:
    text = "Lahore and Ayesha"
    offsets = [(0, 6), (6, 10), (10, 17)]
    labels = ["I-CITY", "O", "I-GIVENNAME"]
    assert merge_token_predictions(text, offsets, labels, [0.9, 1.0, 0.3], threshold=0.5) == [
        PatternFinding("address", 0, 6, 0.9)
    ]
    assert merge_token_predictions(text, offsets, labels, [0.9, 1.0, 0.9], ignore={"address"}) == [
        PatternFinding("person_name", 11, 17, 0.9)
    ]


def test_windows_cover_every_token_with_overlap() -> None:
    assert window_starts(10) == [0]
    starts = window_starts(1000, body=254, overlap=64)
    assert starts[0] == 0 and starts[-1] + 254 >= 1000
    assert all(b - a == 190 for a, b in zip(starts, starts[1:], strict=False))


def test_hybrid_prefers_regex_on_overlap_and_keeps_model_only_spans() -> None:
    text = "Ayesha Khan, CNIC 35202-1234567-1"

    def fake_model(_: str) -> list[PatternFinding]:
        return [PatternFinding("person_name", 0, 11), PatternFinding("id_number", 18, 33)]

    found = HybridDetector(fake_model)(text)
    assert sorted(f.entity_type for f in found) == ["cnic", "person_name"]


def test_passport_pattern_needs_the_keyword_and_reports_only_the_number() -> None:
    from app.privacy.patterns import find_pattern_entities

    text = "My passport is CK7654321 and it expires next year."
    [found] = find_pattern_entities(text)
    assert found.entity_type == "passport" and text[found.start : found.end] == "CK7654321"
    assert find_pattern_entities("Model AB1234567 scored 0.81 on the benchmark.") == []


def test_model_failure_fails_closed_at_the_gate() -> None:
    def broken(_: str) -> list[PatternFinding]:
        raise RuntimeError("CUDA out of memory")

    scanner = PrivacyScanner(HybridDetector(broken), version="piiranha-v1+patterns-v1")
    result = check_outbound(
        b"ordinary public text",
        scanner=scanner,
        mode="cloud_allowed",
        label="public",
        user_id="u",
        session_id="s",
        model_id="m",
    )
    assert not result.allowed and result.reason == "scanner_error"


@pytest.fixture
def fresh_settings(monkeypatch):
    get_settings.cache_clear()
    default_scanner.cache_clear()
    yield monkeypatch
    monkeypatch.setenv("PII_DETECTOR", "patterns")
    get_settings.cache_clear()
    default_scanner.cache_clear()


def test_missing_model_path_fails_closed(fresh_settings, tmp_path) -> None:
    fresh_settings.setenv("PII_DETECTOR", "piiranha")
    fresh_settings.setenv("PII_MODEL_PATH", str(tmp_path / "nowhere"))
    scan = default_scanner().scan("ordinary text", "prompt")
    assert scan.error is not None  # -> cloud removed, never a silent regex-only fallback


def test_unknown_detector_name_fails_closed(fresh_settings) -> None:
    fresh_settings.setenv("PII_DETECTOR", "presidioo")
    assert default_scanner().scan("ordinary text", "prompt").error is not None


# --- real model -----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def model() -> PiiModelDetector:
    return PiiModelDetector(str(MODEL_PATH))


@needs_model
def test_model_detects_synthetic_name_and_email(model) -> None:
    # The model alone labels the local part as a username and can miss whole emails, so the
    # served detector is the hybrid: regex owns emails, the model adds names.
    text = "Please send the grade sheet to Ayesha Siddiqui at ayesha.s@example.test tomorrow."
    types = {f.entity_type for f in HybridDetector(model)(text)}
    assert "person_name" in types and "email" in types


@needs_model
def test_model_finds_entity_beyond_first_window(model) -> None:
    filler = "The transformer architecture relies on attention over token sequences. " * 60
    text = filler + "The reviewer was Bilal Ahmed, phone 0300-1234567."
    found = HybridDetector(model)(text)
    assert any(f.entity_type == "person_name" and f.start > len(filler) - 5 for f in found)
    assert any(f.entity_type == "pk_phone" for f in found)


HIGH_RISK = {"card", "account_number", "password", "id_number", "passport", "iban", "cnic"}


@needs_model
def test_benign_academic_text_has_no_high_risk_findings(model) -> None:
    # Known, accepted false positive: the model reads "BM25" as an address. Findings are shown
    # to the user before any cloud decision (review step), so a false alarm costs one click;
    # high-risk identifier types must still never fire on ordinary academic text.
    text = (
        "We evaluate BM25 retrieval on QASPER and report token F1. "
        "See arXiv 2403.01234 and the 03-2024 report for the ablation table."
    )
    assert not {f.entity_type for f in HybridDetector(model)(text)} & HIGH_RISK


@needs_model
def test_model_detects_high_risk_identifiers(model) -> None:
    cases = {
        "Transfer to account number 0123456789012 at the bank.": "account_number",
        "Login with password: Tr0ub4dor&3 for the portal.": "password",
        "Social security number 123-45-6789.": "id_number",
        "Passport number: AB1234567, issued 2019.": "passport",
    }
    for text, kind in cases.items():
        assert kind in {f.entity_type for f in HybridDetector(model)(text)}, text


@needs_model
def test_redacted_preview_masks_model_entities(model) -> None:
    scanner = PrivacyScanner(HybridDetector(model), version="piiranha-v1+patterns-v1")
    preview = redact("Ask Ayesha Siddiqui about the thesis draft.", scanner)
    assert "Siddiqui" not in preview and "[PERSON_NAME]" in preview
