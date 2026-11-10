"""Synthetic fail-closed privacy regression cases (synthetic identifiers only).

Used by CI (``python -m eval.privacy_suite``) and by the router at runtime: if any
case fails, exploration on cloud models is disabled (docs/05, Phase 9).
"""

import hashlib
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from app.privacy.consent import Consent
from app.privacy.detector import PrivacyScanner
from app.privacy.gate import check_outbound
from app.privacy.policy import InstitutionalPolicy


def _failing_detector(_: str) -> list:
    raise RuntimeError("boom")


def _gate(payload: bytes, **kw):
    base = dict(
        scanner=PrivacyScanner(),
        mode="cloud_allowed",
        label="public",
        user_id="user-1",
        session_id="session-1",
        model_id="model-1",
    )
    base.update(kw)
    return check_outbound(payload, **base)


def run_suite() -> list[tuple[str, object, object]]:
    """Return a list of (case, actual, expected) for every FAILED case (empty = green)."""
    payload = b"Contact synthetic.user@example.test for the test case."
    digest = hashlib.sha256(payload).hexdigest()

    def consent(**kw):
        values = dict(
            user_id="user-1",
            session_id="session-1",
            destination_model_id="model-1",
            payload_hash=digest,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        values.update(kw)
        return Consent(**values)

    cases = [
        (
            "benign lookalike allowed",
            _gate(b"The example.test domain is reserved for documentation.").allowed,
            True,
        ),
        (
            "benign date and paper id allowed",
            _gate(b"See arXiv 2403.01234 and the 03-2024 report.").allowed,
            True,
        ),
        (
            "synthetic email requires consent",
            _gate(payload, label="internal").reason,
            "consent_required",
        ),
        (
            "scoped consent allows exact payload",
            _gate(payload, label="internal", consent=consent()).allowed,
            True,
        ),
        (
            "consent for another model is rejected",
            _gate(payload, label="internal", consent=consent(destination_model_id="other")).reason,
            "consent_required",
        ),
        (
            "consent for a changed payload is rejected",
            _gate(payload + b" more", label="internal", consent=consent()).reason,
            "consent_required",
        ),
        (
            "expired consent is rejected",
            _gate(
                payload,
                label="internal",
                consent=consent(expires_at=datetime.now(UTC) - timedelta(seconds=1)),
            ).reason,
            "consent_required",
        ),
        (
            "revoked consent is rejected",
            _gate(payload, label="internal", consent=consent(revoked_at=datetime.now(UTC))).reason,
            "consent_required",
        ),
        (
            "confidential label blocks cloud with no entities",
            _gate(b"ordinary text", label="confidential").reason,
            "consent_required",
        ),
        (
            "local-only blocks cloud",
            _gate(b"ordinary text", mode="local_only").reason,
            "local_only_mode",
        ),
        (
            "institutional prohibition wins over consent",
            _gate(
                payload,
                label="internal",
                consent=consent(),
                institutional=InstitutionalPolicy(allow_cloud=False),
            ).reason,
            "institutional_cloud_prohibition",
        ),
        (
            "institutional label prohibition",
            _gate(
                b"ordinary text",
                label="internal",
                institutional=InstitutionalPolicy(forbid_labels=frozenset({"internal"})),
            ).reason,
            "institutional_label_prohibition",
        ),
        (
            "scanner failure fails closed",
            _gate(b"ordinary text", scanner=PrivacyScanner(detector=_failing_detector)).reason,
            "scanner_error",
        ),
        (
            "CNIC is detected",
            _gate(b"id 35202-1234567-1", label="internal").reason,
            "consent_required",
        ),
        (
            "PK phone is detected",
            _gate(b"call 0300-1234567", label="internal").reason,
            "consent_required",
        ),
    ]
    return [(name, actual, expected) for name, actual, expected in cases if actual != expected]


@lru_cache(maxsize=1)
def privacy_gate_green() -> bool:
    """True when every synthetic privacy case passes. Cached per process."""
    try:
        return not run_suite()
    except Exception:
        return False
