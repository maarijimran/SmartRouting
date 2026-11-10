"""Immutable policy versions with an active pointer and rollback.

Version "0" (fixed rules) always exists and is the rollback target (invariant 11).
Rows are never updated except for the ``active`` flag.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PolicyVersionRecord
from app.routing.config import routing_config

RULES_VERSION = "0"


@dataclass(frozen=True)
class PolicyVersion:
    name: str
    version: str
    config_hash: str
    created_at: datetime
    active: bool = False


class InMemoryPolicyStore:
    def __init__(self) -> None:
        self._versions: list[PolicyVersion] = []
        self._active: dict[str, str] = {}

    def publish(self, name: str, version: str, config_hash: str) -> PolicyVersion:
        record = PolicyVersion(name, version, config_hash, datetime.now(UTC))
        self._versions.append(record)
        return record

    def activate(self, deployment: str, version: str) -> PolicyVersion:
        record = next((item for item in self._versions if item.version == version), None)
        if record is None:
            raise KeyError(f"Unknown policy version: {version}")
        self._active[deployment] = version
        return PolicyVersion(
            record.name, record.version, record.config_hash, record.created_at, True
        )

    def active(self, deployment: str) -> PolicyVersion | None:
        version = self._active.get(deployment)
        return next((item for item in self._versions if item.version == version), None)

    def rollback(self, deployment: str, version: str = "0") -> PolicyVersion:
        return self.activate(deployment, version)


def config_hash(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def ensure_rules_version(db: Session, deployment: str = "default") -> PolicyVersionRecord:
    record = db.scalar(
        select(PolicyVersionRecord).where(PolicyVersionRecord.version == RULES_VERSION)
    )
    if record is None:
        record = PolicyVersionRecord(
            name="fixed_rules",
            version=RULES_VERSION,
            config_hash=config_hash(routing_config().get("rules", {})),
            deployment=deployment,
            kind="rules",
            active=db.scalar(
                select(PolicyVersionRecord).where(
                    PolicyVersionRecord.deployment == deployment, PolicyVersionRecord.active
                )
            )
            is None,
        )
        db.add(record)
        db.commit()
    return record


def active_record(db: Session, deployment: str = "default") -> PolicyVersionRecord:
    ensure_rules_version(db, deployment)
    record = db.scalar(
        select(PolicyVersionRecord).where(
            PolicyVersionRecord.deployment == deployment, PolicyVersionRecord.active.is_(True)
        )
    )
    return record or ensure_rules_version(db, deployment)


def list_versions(db: Session, deployment: str = "default") -> list[PolicyVersionRecord]:
    ensure_rules_version(db, deployment)
    return list(
        db.scalars(
            select(PolicyVersionRecord)
            .where(PolicyVersionRecord.deployment == deployment)
            .order_by(PolicyVersionRecord.created_at)
        )
    )


def publish_version(
    db: Session,
    *,
    name: str,
    kind: str,
    version: str,
    params: dict,
    epsilon: float | None = None,
    parent_id: str | None = None,
    deployment: str = "default",
    activate: bool = False,
) -> PolicyVersionRecord:
    record = PolicyVersionRecord(
        name=name,
        version=version,
        config_hash=config_hash(params),
        deployment=deployment,
        kind=kind,
        params_json=json.dumps(params),
        epsilon=epsilon,
        parent_id=parent_id,
        active=False,
    )
    db.add(record)
    db.commit()
    if activate:
        activate_version(db, record.id, deployment)
        db.refresh(record)
    return record


def activate_version(
    db: Session, record_id: str, deployment: str = "default"
) -> PolicyVersionRecord:
    target = db.get(PolicyVersionRecord, record_id)
    if target is None or target.deployment != deployment:
        raise KeyError(f"Unknown policy version: {record_id}")
    for row in db.scalars(
        select(PolicyVersionRecord).where(
            PolicyVersionRecord.deployment == deployment, PolicyVersionRecord.active.is_(True)
        )
    ):
        row.active = False
    target.active = True
    db.commit()
    return target


def rollback(db: Session, deployment: str = "default") -> PolicyVersionRecord:
    """Re-activate the parent of the active version, or fixed rules if there is none."""
    current = active_record(db, deployment)
    target = db.get(PolicyVersionRecord, current.parent_id) if current.parent_id else None
    if target is None or target.id == current.id:
        target = ensure_rules_version(db, deployment)
    return activate_version(db, target.id, deployment)
