import asyncio
import base64
from datetime import UTC, datetime, timedelta

import pytest
from app.adapters.base import GenerationParams
from app.adapters.fake import FakeAdapter
from app.gateway.egress import EgressBlocked, send_cloud
from app.keys.vault import seal_provider_key
from app.privacy.consent import Consent
from app.privacy.detector import PrivacyScanner
from app.privacy.gate import check_outbound
from app.privacy.labels import derived_label
from app.privacy.policy import CloudEligibilityContext, InstitutionalPolicy, eligibility_for_cloud


def test_patterns_detect_pk_identifiers_and_ignore_date() -> None:
    result = PrivacyScanner().scan(
        "Email test@example.com, phone 0300-1234567, CNIC 35202-1234567-1, date 03-2024",
        "prompt",
    )
    kinds = {finding.entity_type for finding in result.findings}
    assert {"email", "pk_phone", "cnic"} <= kinds
    assert "student_id" not in kinds


def test_scanner_errors_fail_closed() -> None:
    def broken(_: str):
        raise RuntimeError("detector unavailable")

    result = PrivacyScanner(broken).scan("safe", "prompt")
    assert result.error is not None
    allowed, reason = eligibility_for_cloud(
        CloudEligibilityContext("cloud_allowed", "public", result, None, "u", "s", "m", "hash")
    )
    assert not allowed
    assert reason == "scanner_error"


def test_local_only_and_confidential_require_consent() -> None:
    scan = PrivacyScanner().scan("safe", "prompt")
    local, local_reason = eligibility_for_cloud(
        CloudEligibilityContext("local_only", "public", scan, None, "u", "s", "m", "hash")
    )
    confidential, reason = eligibility_for_cloud(
        CloudEligibilityContext(
            "cloud_allowed",
            "confidential",
            scan,
            None,
            "u",
            "s",
            "m",
            "hash",
        )
    )
    assert not local and local_reason == "local_only_mode"
    assert not confidential and reason == "consent_required"


def test_consent_scope_expiry_revocation_and_institutional_override() -> None:
    expiry = datetime.now(UTC) + timedelta(minutes=5)
    consent = Consent("u", "s", "m", "hash", expiry)
    scan = PrivacyScanner().scan("email test@example.com", "payload")
    context = CloudEligibilityContext(
        "cloud_allowed", "public", scan, consent, "u", "s", "m", "hash"
    )
    assert eligibility_for_cloud(context)[0]
    assert not eligibility_for_cloud(
        CloudEligibilityContext("cloud_allowed", "public", scan, consent, "u", "s", "other", "hash")
    )[0]
    assert not eligibility_for_cloud(
        CloudEligibilityContext(
            "cloud_allowed",
            "public",
            scan,
            Consent("u", "s", "m", "hash", expiry, datetime.now(UTC)),
            "u",
            "s",
            "m",
            "hash",
        )
    )[0]
    assert not eligibility_for_cloud(
        CloudEligibilityContext(
            "cloud_allowed",
            "public",
            scan,
            consent,
            "u",
            "s",
            "m",
            "hash",
            InstitutionalPolicy(False),
        )
    )[0]


def test_labels_propagate_and_gate_blocks_canary_before_sink() -> None:
    assert derived_label("public", "confidential") == "confidential"
    payload = b"canary test@example.com"
    result = check_outbound(
        payload,
        scanner=PrivacyScanner(),
        mode="cloud_allowed",
        label="public",
        user_id="u",
        session_id="s",
        model_id="m",
    )
    assert not result.allowed

    key = seal_provider_key("provider-secret", base64.b64encode(b"6" * 32).decode())
    called = False

    def factory(_: str):
        nonlocal called
        called = True
        return FakeAdapter()

    async def dispatch():
        return [
            item
            async for item in send_cloud(
                factory,
                key,
                base64.b64encode(b"6" * 32).decode(),
                [],
                GenerationParams(),
                privacy_gate=True,
                gate_result=result,
            )
        ]

    with pytest.raises(EgressBlocked):
        asyncio.run(dispatch())
    assert not called
