"""Feedback storage and scored-outcome computation (docs/03, docs/05)."""

import logging
from itertools import cycle

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Feedback,
    Message,
    PrivacyFinding,
    RatingAssignment,
    RatingItem,
    RoutingAttempt,
    RoutingEvent,
    ScoredOutcome,
    User,
)
from app.feedback.agreement import cohen_kappa
from app.routing.reward import (
    FAILURE_REWARD,
    RewardConfig,
    combine_quality,
    human_score,
    reward,
)

DIMENSIONS = ("correctness", "relevance", "completeness", "usefulness")


def _is_sensitive(db: Session, event: RoutingEvent) -> bool:
    if event.effective_label == "confidential":
        return True
    has_findings = db.scalar(select(PrivacyFinding.id).where(PrivacyFinding.event_id == event.id))
    return has_findings is not None


def score_event(
    db: Session, event_id: str, config: RewardConfig | None = None
) -> ScoredOutcome | None:
    """Compute (or defer) the scored outcome for the policy's selected action.

    - privacy blocks and abstentions are excluded from learning;
    - a failed/empty/timeout selected attempt has R = -1 with its incurred cost;
    - otherwise R needs a quality signal; with none, the update is deferred.
    """
    config = config or RewardConfig.load()
    event = db.get(RoutingEvent, event_id)
    if event is None or event.abstained or not event.selected_model:
        return None
    attempts = list(
        db.scalars(
            select(RoutingAttempt)
            .where(RoutingAttempt.event_id == event.id)
            .order_by(RoutingAttempt.attempt_no)
        )
    )
    selected = next((a for a in attempts if a.model == event.selected_model), None)
    if selected is None or selected.status == "blocked":
        return None
    cost = sum(a.measured_cost_usd or 0.0 for a in attempts if a.status != "blocked")
    latency = event.generation_latency_ms or selected.latency_ms or 0.0
    usable = not _is_sensitive(db, event)

    quality, source, value = None, None, None
    if selected.status != "ok":
        value, source = FAILURE_REWARD, "failure"
        cost = selected.measured_cost_usd or 0.0
    else:
        rows = list(db.scalars(select(Feedback).where(Feedback.event_id == event.id)))
        humans = [
            human_score(*(getattr(r, d) for d in DIMENSIONS))
            for r in rows
            if all(getattr(r, d) is not None for d in DIMENSIONS)
        ]
        autos = [r.auto_score for r in rows if r.auto_score is not None]
        quality, source = combine_quality(
            sum(humans) / len(humans) if humans else None,
            sum(autos) / len(autos) if autos else None,
            config,
        )
        if quality is None:
            return None  # defer: no quality signal yet
        value = reward(quality, cost, latency, config)

    outcome = db.get(ScoredOutcome, event.id) or ScoredOutcome(event_id=event.id, model="")
    outcome.model = event.selected_model
    outcome.quality = quality
    outcome.q_source = source
    outcome.reward = value
    outcome.cost_usd = cost
    outcome.latency_ms = latency
    outcome.features_json = event.features_json
    outcome.usable_for_update = usable
    db.add(outcome)
    db.commit()
    _after_scoring(db)
    return outcome


def _after_scoring(db: Session) -> None:
    """Best-effort online learning + rollback checks; never breaks the request path."""
    try:
        from app.routing.learner import check_rollback_triggers, maybe_update

        maybe_update(db)
        check_rollback_triggers(db)
    except Exception:  # pragma: no cover - logged, not raised
        logging.getLogger("smartroute.learner").exception("learner step failed")


def submit_user_feedback(
    db: Session, user_id: str, event_id: str, ratings: dict[str, int]
) -> ScoredOutcome | None:
    event = db.get(RoutingEvent, event_id)
    if event is None or event.user_id != user_id:
        raise LookupError("event not found")
    db.add(Feedback(event_id=event_id, rater_id=user_id, source="user", blind=False, **ratings))
    db.commit()
    return score_event(db, event_id)


# --- rater workflow ----------------------------------------------------------


def create_item(
    db: Session,
    *,
    prompt: str,
    response: str,
    model: str,
    task_type: str = "qa",
    evidence: str = "",
    event_id: str | None = None,
) -> RatingItem:
    item = RatingItem(
        prompt=prompt,
        response=response,
        model=model,
        task_type=task_type,
        evidence=evidence,
        event_id=event_id,
    )
    db.add(item)
    db.commit()
    return item


def enqueue_events(db: Session, limit: int = 120) -> int:
    """Stratified (by task) queue of non-sensitive, answered events with live content."""
    events = list(
        db.scalars(
            select(RoutingEvent)
            .where(RoutingEvent.status == "succeeded")
            .order_by(RoutingEvent.created_at.desc())
        )
    )
    already = {i.event_id for i in db.scalars(select(RatingItem)) if i.event_id}
    by_task: dict[str, list[RoutingEvent]] = {}
    for event in events:
        if event.id in already or _is_sensitive(db, event):
            continue
        by_task.setdefault(event.task_type or "qa", []).append(event)
    created = 0
    queues = [list(v) for v in by_task.values()]
    while queues and created < limit:
        for queue in list(queues):
            if created >= limit:
                break
            if not queue:
                queues.remove(queue)
                continue
            event = queue.pop(0)
            answer = db.scalar(select(Message).where(Message.event_id == event.id))
            prompt = db.scalar(
                select(Message)
                .where(Message.session_id == event.session_id, Message.role == "user")
                .where(Message.created_at <= (answer.created_at if answer else event.created_at))
                .order_by(Message.created_at.desc())
            )
            if answer is None or prompt is None:
                continue  # raw content already purged
            create_item(
                db,
                prompt=prompt.content,
                response=answer.content,
                model=event.selected_model or "",
                task_type=event.task_type or "qa",
                event_id=event.id,
            )
            created += 1
    return created


def assign_items(db: Session, raters_per_item: int = 2) -> int:
    raters = list(db.scalars(select(User).where(User.role == "rater", User.is_active.is_(True))))
    if len(raters) < raters_per_item:
        raise ValueError(f"need at least {raters_per_item} active raters")
    assigned = {a.item_id for a in db.scalars(select(RatingAssignment))}
    ring = cycle(raters)
    count = 0
    for item in db.scalars(select(RatingItem)):
        if item.id in assigned:
            continue
        chosen = []
        while len(chosen) < raters_per_item:
            rater = next(ring)
            if rater not in chosen:
                chosen.append(rater)
        for rater in chosen:
            db.add(RatingAssignment(item_id=item.id, rater_id=rater.id))
        count += 1
    db.commit()
    return count


def rater_queue(db: Session, rater_id: str) -> list[dict]:
    """Blind payload: no model name, no event id, nothing that identifies the route."""
    rows = db.execute(
        select(RatingItem, RatingAssignment)
        .join(RatingAssignment, RatingAssignment.item_id == RatingItem.id)
        .where(RatingAssignment.rater_id == rater_id, RatingAssignment.done_at.is_(None))
        .order_by(RatingItem.created_at)
    ).all()
    return [
        {
            "item_id": item.id,
            "task_type": item.task_type,
            "prompt": item.prompt,
            "evidence": item.evidence,
            "response": item.response,
        }
        for item, _ in rows
    ]


def submit_item_rating(db: Session, rater_id: str, item_id: str, ratings: dict[str, int]) -> None:
    from datetime import UTC, datetime

    assignment = db.scalar(
        select(RatingAssignment).where(
            RatingAssignment.item_id == item_id,
            RatingAssignment.rater_id == rater_id,
            RatingAssignment.done_at.is_(None),
        )
    )
    if assignment is None:
        raise LookupError("no open assignment")
    item = db.get(RatingItem, item_id)
    db.add(
        Feedback(
            item_id=item_id,
            event_id=item.event_id,
            rater_id=rater_id,
            source="rater",
            blind=True,
            **ratings,
        )
    )
    assignment.done_at = datetime.now(UTC)
    db.commit()
    if item.event_id:
        score_event(db, item.event_id)


def agreement_report(db: Session) -> dict:
    """Weighted kappa per dimension over items rated by exactly two raters."""
    by_item: dict[str, list[Feedback]] = {}
    for row in db.scalars(select(Feedback).where(Feedback.source == "rater")):
        by_item.setdefault(row.item_id or "", []).append(row)
    pairs = [rows[:2] for rows in by_item.values() if len(rows) >= 2]
    report: dict = {"items": len(pairs), "kappa": {}}
    for dim in DIMENSIONS:
        a = [getattr(p[0], dim) for p in pairs if getattr(p[0], dim) and getattr(p[1], dim)]
        b = [getattr(p[1], dim) for p in pairs if getattr(p[0], dim) and getattr(p[1], dim)]
        report["kappa"][dim] = round(cohen_kappa(a, b), 4) if a else None
    return report


def source_bias_report(db: Session) -> dict:
    """Mean human score by feedback source (user vs rater) to expose source bias."""
    sums: dict[str, list[float]] = {}
    for row in db.scalars(select(Feedback)):
        if all(getattr(row, d) is not None for d in DIMENSIONS):
            sums.setdefault(row.source, []).append(
                human_score(*(getattr(row, d) for d in DIMENSIONS))
            )
    return {
        source: {"n": len(v), "mean_H": round(sum(v) / len(v), 4)} for source, v in sums.items()
    } | {"note": "compare sources before pooling ratings"}
