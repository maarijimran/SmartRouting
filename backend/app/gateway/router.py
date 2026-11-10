import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.context.token_count import count_text
from app.core.config import get_settings
from app.core.ratelimit import rate_limit
from app.db.models import (
    ChatSession,
    Chunk,
    Document,
    Message,
    RoutingAttempt,
    RoutingEvent,
)
from app.db.session import get_db
from app.gateway.pipeline import run_pipeline
from app.gateway.service import (
    ChatRequest,
    persist_turn,
    prepare_turn,
    probe_local_health,
)
from app.routing.policies import load_policies

router = APIRouter(prefix="/api/v1", tags=["gateway"])
Db = Annotated[Session, Depends(get_db)]
User = Annotated[dict[str, str], Depends(current_user)]


class SessionPatch(BaseModel):
    mode: Literal["local_only", "cloud_allowed"] | None = None
    label: Literal["public", "internal", "confidential"] | None = None
    persist_opt_in: bool | None = None


class DocumentPatch(BaseModel):
    label: Literal["public", "internal", "confidential"]


def _owned_session(db: Session, session_id: str, user_id: str) -> ChatSession:
    session = db.scalar(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return session


def _session_json(session: ChatSession) -> dict:
    return {
        "id": session.id,
        "mode": session.mode,
        "label": session.label,
        "persist_opt_in": session.persist_opt_in,
        "expires_at": session.expires_at.isoformat(),
    }


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


@router.get("/sessions")
def list_sessions(user: User, db: Db) -> list[dict]:
    rows = db.scalars(
        select(ChatSession)
        .where(ChatSession.user_id == user["id"])
        .order_by(ChatSession.last_active_at.desc())
    )
    return [_session_json(row) for row in rows]


@router.patch("/sessions/{session_id}")
def patch_session(session_id: str, payload: SessionPatch, user: User, db: Db) -> dict:
    session = _owned_session(db, session_id, user["id"])
    if payload.mode is not None:
        session.mode = payload.mode
    if payload.label is not None:
        session.label = payload.label
    if payload.persist_opt_in is not None:
        session.persist_opt_in = payload.persist_opt_in
    db.commit()
    return _session_json(session)


@router.get("/sessions/{session_id}/messages")
def list_messages(session_id: str, user: User, db: Db) -> list[dict]:
    session = _owned_session(db, session_id, user["id"])
    rows = db.scalars(
        select(Message).where(Message.session_id == session.id).order_by(Message.created_at)
    )
    events = {}
    result = []
    for row in rows:
        entry = {
            "id": row.id,
            "role": row.role,
            "content": row.content,
            "label": row.label,
            "event_id": row.event_id,
        }
        if row.event_id:
            if row.event_id not in events:
                events[row.event_id] = db.get(RoutingEvent, row.event_id)
            event = events[row.event_id]
            entry["route"] = event_json(db, event) if event else None
        result.append(entry)
    return result


@router.get("/sessions/{session_id}/documents")
def list_documents(session_id: str, user: User, db: Db) -> list[dict]:
    session = _owned_session(db, session_id, user["id"])
    rows = db.scalars(select(Document).where(Document.session_id == session.id))
    return [{"id": d.id, "filename": d.filename, "pages": d.pages, "label": d.label} for d in rows]


@router.patch("/documents/{document_id}")
def patch_document(document_id: str, payload: DocumentPatch, user: User, db: Db) -> dict:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    _owned_session(db, document.session_id, user["id"])
    document.label = payload.label
    db.execute(
        Chunk.__table__.update().where(Chunk.document_id == document.id).values(label=payload.label)
    )
    db.commit()
    return {"id": document.id, "label": document.label}


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, user: User, db: Db) -> None:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    _owned_session(db, document.session_id, user["id"])
    db.execute(delete(Chunk).where(Chunk.document_id == document.id))
    db.delete(document)
    db.commit()


def event_json(db: Session, event: RoutingEvent) -> dict:
    """Route-panel view of a stored event: estimated and measured kept separate."""
    attempts = db.scalars(
        select(RoutingAttempt)
        .where(RoutingAttempt.event_id == event.id)
        .order_by(RoutingAttempt.attempt_no)
    )
    return {
        "event_id": event.id,
        "status": event.status,
        "model": event.selected_model,
        "policy": event.policy_name,
        "policy_version": event.policy_version,
        "rule_id": event.rule_id,
        "reason": event.explanation,
        "probability": event.action_prob,
        "task": event.task_type,
        "label": event.effective_label,
        "eligible": json.loads(event.eligible_json or "[]"),
        "removed": json.loads(event.removed_json or "[]"),
        "estimated": {
            "input_tokens": event.estimated_input_tokens,
            "output_tokens": event.estimated_output_tokens,
            "cost_usd": event.estimated_cost_usd,
            "latency_ms": event.estimated_latency_ms,
        },
        "measured": {
            "input_tokens": event.measured_input_tokens,
            "output_tokens": event.measured_output_tokens,
            "cost_usd": event.measured_cost_usd,
            "latency_ms": event.generation_latency_ms,
            "ttft_ms": event.ttft_ms,
        },
        "routing_latency_ms": event.routing_latency_ms,
        "attempts": [
            {"model": a.model, "status": a.status, "error_class": a.error_class} for a in attempts
        ],
    }


@router.get("/events/{event_id}")
def get_event(event_id: str, user: User, db: Db) -> dict:
    event = db.get(RoutingEvent, event_id)
    if event is None or event.user_id != user["id"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    return event_json(db, event)


@router.post(
    "/sessions/{session_id}/chat",
    dependencies=[Depends(rate_limit("chat", lambda: get_settings().chat_rate_per_min))],
)
def chat(session_id: str, payload: ChatRequest, user: User, db: Db) -> StreamingResponse:
    session = _owned_session(db, session_id, user["id"])
    settings = get_settings()
    prepared = prepare_turn(db, user["id"], session, payload, settings)
    user_message = Message(
        session_id=session.id,
        role="user",
        content=payload.prompt,
        label=prepared.effective_label,
        tokens=count_text(payload.prompt),
    )
    db.add(user_message)
    now = datetime.now(UTC)
    session.last_active_at = now
    session.expires_at = now + timedelta(minutes=60)
    db.commit()
    policy, shadow = load_policies(db)

    async def stream() -> AsyncIterator[bytes]:
        candidates = await probe_local_health(prepared.candidates, settings)
        records: dict = {"attempts": []}
        answer: list[str] = []

        def on_record(kind: str, data: dict) -> None:
            if kind == "attempt":
                records["attempts"].append(data)
            else:
                records[kind] = data

        yield _sse(
            "context",
            {
                "label": prepared.effective_label,
                "mode": session.mode,
                "evidence": prepared.evidence_refs,
                "findings": prepared.findings,
            },
        )
        if prepared.compression is not None:
            yield _sse(
                "compression_notice",
                {
                    "compressed_turns": prepared.compression.compressed_turns,
                    "label": prepared.compression.label,
                    "message": "Older turns were summarised locally to fit the context window.",
                },
            )
        async for event in run_pipeline(
            prepared.request,
            candidates,
            policy=policy,
            shadow_policy=shadow,
            on_record=on_record,
        ):
            if event.type == "token":
                answer.append(event.data["text"])
                yield _sse("token", event.data)
            elif event.type in {"done", "abstain", "error"}:
                stored = persist_turn(db, user["id"], session, prepared, records, "".join(answer))
                if event.type == "abstain":
                    # An abstained turn leaves no history, so a retry after the user grants
                    # consent serialises to the identical payload the consent was bound to.
                    db.delete(user_message)
                    db.commit()
                yield _sse(event.type, {**event.data, "event_id": stored.id})
            else:
                yield _sse(event.type, event.data)

    return StreamingResponse(stream(), media_type="text/event-stream")
