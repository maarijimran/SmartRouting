"""Online learner: buffers scored outcomes, refits in batches, publishes immutable versions.

Also contains the rollback triggers (reward drop, error spike, privacy-gate red).
"""

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PolicyVersionRecord, RoutingEvent, ScoredOutcome
from app.privacy.suite import privacy_gate_green
from app.routing import policy_store
from app.routing.bandit import EpsilonGreedyRidge, Outcome, Scaler
from app.routing.config import routing_config

log = logging.getLogger("smartroute.learner")


def _to_outcome(row: ScoredOutcome) -> Outcome:
    return Outcome(row.model, json.loads(row.features_json or "{}"), float(row.reward))


def _eligible_rows(db: Session) -> list[ScoredOutcome]:
    return list(
        db.scalars(
            select(ScoredOutcome)
            .where(ScoredOutcome.usable_for_update.is_(True), ScoredOutcome.reward.is_not(None))
            .order_by(ScoredOutcome.created_at)
        )
    )


def latest_bandit(db: Session) -> PolicyVersionRecord | None:
    return db.scalar(
        select(PolicyVersionRecord)
        .where(PolicyVersionRecord.kind == "bandit")
        .order_by(PolicyVersionRecord.created_at.desc())
        .limit(1)
    )


def maybe_update(db: Session, *, force: bool = False) -> PolicyVersionRecord | None:
    """Publish a new bandit version once ``update_every`` fresh outcomes have accumulated.

    Only the selected action's outcome ever enters a regressor, and only the models
    that appear in the fresh batch are refit. The previous version is untouched.
    """
    cfg = routing_config().get("bandit", {})
    every = int(cfg.get("update_every", 50))
    rows = _eligible_rows(db)
    fresh = [r for r in rows if r.consumed_by is None]
    if not fresh or (len(fresh) < every and not force):
        return None
    parent = latest_bandit(db)
    if parent is not None:
        base = EpsilonGreedyRidge.from_params(json.loads(parent.params_json or "{}"), version="x")
    else:
        base = EpsilonGreedyRidge(
            {},
            {},
            Scaler(),
            version="x",
            lam=float(cfg.get("ridge_lambda", 1.0)),
            cold_start_min=int(cfg.get("cold_start_min", 50)),
            epsilon_initial=float(cfg.get("initial_epsilon", 0.10)),
            epsilon_final=float(cfg.get("final_epsilon", 0.02)),
            epsilon_decay=int(cfg.get("decay_decisions", 1000)),
            window=cfg.get("window"),
        )
    # a refit sees the full history of each affected model (or its sliding window)
    affected = {r.model for r in fresh}
    history = [_to_outcome(r) for r in rows if r.model in affected]
    updated = base.update(history)
    # `update` accumulates counts; for refits on full history, counts equal data size
    for slug in affected:
        updated.counts[slug] = sum(1 for o in history if o.model == slug)
    updated.decisions = base.decisions + len(fresh)
    version = f"bandit-{db.query(PolicyVersionRecord).filter_by(kind='bandit').count() + 1}"
    updated.version = version
    active = policy_store.active_record(db)
    record = policy_store.publish_version(
        db,
        name="adaptive_bandit",
        kind="bandit",
        version=version,
        params=updated.to_params(),
        epsilon=updated.epsilon,
        parent_id=active.id,
        activate=bool(cfg.get("auto_promote", False)),
    )
    for row in fresh:
        row.consumed_by = version
    db.commit()
    log.info("published %s from %d fresh outcomes", version, len(fresh))
    return record


def check_rollback_triggers(db: Session) -> str | None:
    """Roll back to the previous version when a trigger fires. Returns the reason, if any."""
    active = policy_store.active_record(db)
    if active.kind == "rules":
        return None
    cfg = routing_config().get("rollback", {})
    window = int(cfg.get("min_window", 30))
    reason = None
    if not privacy_gate_green():
        reason = "privacy_gate_red"
    else:
        recent = list(
            db.scalars(
                select(ScoredOutcome)
                .join(RoutingEvent, RoutingEvent.id == ScoredOutcome.event_id)
                .where(
                    RoutingEvent.policy_version == active.version,
                    ScoredOutcome.reward.is_not(None),
                )
                .order_by(ScoredOutcome.created_at.desc())
                .limit(window)
            )
        )
        if len(recent) >= window:
            mean_reward = sum(r.reward for r in recent) / len(recent)
            error_rate = sum(1 for r in recent if r.reward == -1.0) / len(recent)
            baseline = list(
                db.scalars(
                    select(ScoredOutcome.reward)
                    .join(RoutingEvent, RoutingEvent.id == ScoredOutcome.event_id)
                    .where(
                        RoutingEvent.policy_name == "fixed_rules",
                        ScoredOutcome.reward.is_not(None),
                    )
                    .limit(500)
                )
            )
            if error_rate > float(cfg.get("error_rate_max", 0.30)):
                reason = "error_spike"
            elif baseline and mean_reward < sum(baseline) / len(baseline) - float(
                cfg.get("reward_drop_delta", 0.05)
            ):
                reason = "reward_drop"
    if reason:
        policy_store.rollback(db)
        log.warning("auto rollback from %s: %s", active.version, reason)
    return reason
