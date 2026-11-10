from dataclasses import dataclass

from app.privacy.consent import Consent
from app.privacy.detector import ScanResult


@dataclass(frozen=True)
class InstitutionalPolicy:
    allow_cloud: bool = True
    forbid_labels: frozenset[str] = frozenset()


@dataclass(frozen=True)
class CloudEligibilityContext:
    mode: str
    label: str
    scan: ScanResult
    consent: Consent | None
    user_id: str
    session_id: str
    model_id: str
    payload_hash: str
    institutional: InstitutionalPolicy = InstitutionalPolicy()


def eligibility_for_cloud(ctx: CloudEligibilityContext) -> tuple[bool, str]:
    if ctx.mode == "local_only":
        return False, "local_only_mode"
    if not ctx.institutional.allow_cloud:
        return False, "institutional_cloud_prohibition"
    if ctx.label in ctx.institutional.forbid_labels:
        return False, "institutional_label_prohibition"
    if ctx.scan.error:
        return False, "scanner_error"
    if ctx.label == "confidential" or ctx.scan.sensitive:
        if ctx.consent is None or not ctx.consent.valid_for(
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            model_id=ctx.model_id,
            payload_hash=ctx.payload_hash,
        ):
            return False, "consent_required"
    return True, "eligible"
