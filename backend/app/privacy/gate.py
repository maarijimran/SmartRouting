import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass

from app.privacy.consent import Consent
from app.privacy.detector import PrivacyScanner
from app.privacy.policy import CloudEligibilityContext, InstitutionalPolicy, eligibility_for_cloud


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    reason: str
    payload_hash: str


def serialize_payload(messages: Sequence[dict[str, str]]) -> bytes:
    """Canonical bytes of exactly what would leave the trust boundary.

    Consent hashes and the egress re-scan both use this one serialisation, so a
    consent is bound to the precise payload and any change invalidates it.
    """
    clean = [{"role": m["role"], "content": m["content"]} for m in messages]
    return json.dumps(clean, ensure_ascii=False, sort_keys=True).encode("utf-8")


def check_outbound(
    payload: bytes,
    *,
    scanner: PrivacyScanner,
    mode: str,
    label: str,
    user_id: str,
    session_id: str,
    model_id: str,
    consent: Consent | None = None,
    institutional: InstitutionalPolicy = InstitutionalPolicy(),
) -> GateResult:
    payload_hash = hashlib.sha256(payload).hexdigest()
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return GateResult(False, "scanner_error", payload_hash)
    scan = scanner.scan(text, "payload")
    allowed, reason = eligibility_for_cloud(
        CloudEligibilityContext(
            mode, label, scan, consent, user_id, session_id, model_id, payload_hash, institutional
        )
    )
    return GateResult(allowed, reason, payload_hash)


def redact(text: str, scanner: PrivacyScanner | None = None) -> str:
    """Return text with detected entities replaced by [TYPE] markers (for previews)."""
    from app.privacy.patterns import find_pattern_entities

    detector = scanner.detector if scanner else find_pattern_entities
    try:
        spans = sorted(detector(text), key=lambda item: item.start, reverse=True)
    except Exception:
        return "[preview unavailable: detector error]"
    for span in spans:
        text = f"{text[: span.start]}[{span.entity_type.upper()}]{text[span.end :]}"
    return text
