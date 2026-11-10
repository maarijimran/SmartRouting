from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    ChatSession,
    Chunk,
    Document,
    Message,
    PrivacyFinding,
    RoutingAttempt,
    RoutingEvent,
)

METADATA_RETENTION_DAYS = 30


def purge_expired_sessions(db: Session, now: datetime | None = None) -> int:
    """Remove raw session content (docs, chunks, messages) after 60 minutes of inactivity."""
    current = now or datetime.now(UTC)
    session_ids = db.scalars(
        select(ChatSession.id).where(
            ChatSession.expires_at <= current,
            ChatSession.persist_opt_in.is_(False),
        )
    ).all()
    if not session_ids:
        return 0
    document_ids = db.scalars(select(Document.id).where(Document.session_id.in_(session_ids))).all()
    if document_ids:
        db.execute(delete(Chunk).where(Chunk.document_id.in_(document_ids)))
        db.execute(delete(Document).where(Document.id.in_(document_ids)))
    db.execute(delete(Message).where(Message.session_id.in_(session_ids)))
    db.execute(delete(ChatSession).where(ChatSession.id.in_(session_ids)))
    db.commit()
    return len(session_ids)


def purge_old_metadata(
    db: Session, now: datetime | None = None, days: int = METADATA_RETENTION_DAYS
) -> int:
    """Delete routing metadata (events, attempts, findings) older than the retention window.

    Scored outcomes are kept: they hold only coarse features, numbers and IDs.
    """
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    ids = db.scalars(select(RoutingEvent.id).where(RoutingEvent.created_at < cutoff)).all()
    if not ids:
        return 0
    db.execute(delete(RoutingAttempt).where(RoutingAttempt.event_id.in_(ids)))
    db.execute(delete(PrivacyFinding).where(PrivacyFinding.event_id.in_(ids)))
    db.execute(delete(RoutingEvent).where(RoutingEvent.id.in_(ids)))
    db.commit()
    return len(ids)


def run_retention(db: Session, now: datetime | None = None) -> dict[str, int]:
    return {
        "sessions_purged": purge_expired_sessions(db, now),
        "events_purged": purge_old_metadata(db, now),
    }
