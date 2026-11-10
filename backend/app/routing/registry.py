"""Builds learned policies from immutable policy_versions rows and finds the shadow candidate."""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PolicyVersionRecord
from app.privacy.suite import privacy_gate_green
from app.routing.bandit import EpsilonGreedyRidge
from app.routing.config import routing_config
from app.routing.frozen import FrozenRouter


def build_learned_policy(record: PolicyVersionRecord, db: Session):
    params = json.loads(record.params_json or "{}")
    if record.kind == "bandit":
        # Cloud exploration is allowed only while the synthetic privacy suite is green.
        return EpsilonGreedyRidge.from_params(
            params, version=record.version, cloud_exploration=privacy_gate_green()
        )
    if record.kind == "frozen":
        return FrozenRouter.from_params(params, version=record.version)
    raise ValueError(f"Unknown policy kind: {record.kind}")


def shadow_candidate(db: Session):
    """Latest learned (bandit) version, run beside the fixed rules in shadow mode."""
    if not routing_config().get("bandit", {}).get("shadow_mode", True):
        return None
    record = db.scalar(
        select(PolicyVersionRecord)
        .where(PolicyVersionRecord.kind == "bandit")
        .order_by(PolicyVersionRecord.created_at.desc())
        .limit(1)
    )
    return build_learned_policy(record, db) if record else None
