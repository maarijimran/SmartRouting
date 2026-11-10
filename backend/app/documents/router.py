import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.context.token_count import count_text
from app.core.config import get_settings
from app.core.ratelimit import rate_limit
from app.db.models import ChatSession, Chunk, Document, Message
from app.db.session import get_db
from app.documents.chunk import chunk_document
from app.documents.parse import DocumentParseError, parse_document

router = APIRouter(prefix="/api/v1/sessions", tags=["documents"])
Db = Annotated[Session, Depends(get_db)]
User = Annotated[dict[str, str], Depends(current_user)]


def _owned_session(db: Session, session_id: str, user_id: str) -> ChatSession:
    session = db.scalar(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return session


@router.post("", status_code=status.HTTP_201_CREATED)
def create_session(user: User, db: Db) -> dict[str, str]:
    now = datetime.now(UTC)
    session = ChatSession(user_id=user["id"], expires_at=now + timedelta(minutes=60))
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"id": session.id, "mode": session.mode, "label": session.label}


@router.post(
    "/{session_id}/documents",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("upload", lambda: get_settings().upload_rate_per_min))],
)
async def upload_document(session_id: str, user: User, db: Db, file: UploadFile = File(...)):
    session = _owned_session(db, session_id, user["id"])
    content = await file.read()
    try:
        parsed = parse_document(file.filename or "upload", content, file.content_type)
    except DocumentParseError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    document = Document(
        session_id=session.id,
        filename=parsed.filename,
        pages=len(parsed.pages),
        bytes=len(content),
        text=parsed.text,
        label=session.label,
    )
    db.add(document)
    db.flush()
    for chunk in chunk_document(parsed):
        db.add(
            Chunk(
                # content hash alone collides when the same file is uploaded twice
                id=hashlib.sha256(f"{document.id}:{chunk.id}".encode()).hexdigest()[:24],
                document_id=document.id,
                idx=chunk.index,
                page=chunk.page,
                text=chunk.text,
                tokens=count_text(chunk.text),
                label=chunk.label,
            )
        )
    session.last_active_at = datetime.now(UTC)
    session.expires_at = datetime.now(UTC) + timedelta(minutes=60)
    db.commit()
    return {"id": document.id, "filename": document.filename, "pages": str(document.pages)}


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str, user: User, db: Db) -> None:
    session = _owned_session(db, session_id, user["id"])
    db.execute(delete(Message).where(Message.session_id == session.id))
    document_ids = db.scalars(select(Document.id).where(Document.session_id == session.id)).all()
    if document_ids:
        db.execute(delete(Chunk).where(Chunk.document_id.in_(document_ids)))
        db.execute(delete(Document).where(Document.id.in_(document_ids)))
    db.delete(session)
    db.commit()
