"""Resolves the serving policy (and optional shadow policy) from the policy store."""

from sqlalchemy.orm import Session

from app.routing.policy_store import RULES_VERSION, active_record
from app.routing.rules import FixedRules, Policy


def build_policy(record, db: Session) -> Policy:
    """Instantiate the policy described by an immutable policy_versions row."""
    if record.kind == "rules":
        return FixedRules()
    from app.routing.registry import build_learned_policy  # Phase 9

    return build_learned_policy(record, db)


def load_policies(db: Session) -> tuple[Policy, Policy | None]:
    """Return (serving policy, shadow policy).

    A learned policy only serves when it is the active version and passes the
    cold-start check; otherwise fixed rules serve. When fixed rules serve and a
    learned policy exists, the learned policy runs in shadow mode.
    """
    record = active_record(db)
    rules = FixedRules()
    if record.kind == "rules" or record.version == RULES_VERSION:
        try:
            from app.routing.registry import shadow_candidate

            return rules, shadow_candidate(db)
        except ImportError:
            return rules, None
    policy = build_policy(record, db)
    if not getattr(policy, "ready", True):
        return rules, policy
    return policy, None
