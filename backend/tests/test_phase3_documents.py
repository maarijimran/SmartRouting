import base64
import os
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path('test_documents.db').absolute()}"
os.environ["KEY_VAULT_MASTER_KEY"] = base64.b64encode(b"5" * 32).decode()

import pytest
from app.context.builder import build_context
from app.context.compress import compress_history
from app.context.token_count import fits_context
from app.db.models import ChatSession, Chunk, Document, RefreshToken, User
from app.db.session import SessionLocal, init_db
from app.documents.chunk import chunk_document
from app.documents.classify import classify_task
from app.documents.parse import DocumentParseError, parse_document
from app.documents.retrieve import Retriever
from app.documents.service import purge_expired_sessions
from app.main import app
from fastapi.testclient import TestClient


def test_txt_parse_chunk_and_retrieve() -> None:
    parsed = parse_document("paper.txt", b"alpha result. beta method. alpha conclusion.")
    chunks = chunk_document(parsed, words_per_chunk=2)
    evidence = Retriever(chunks).search("conclusion", top_k=1)
    assert parsed.text.startswith("alpha result")
    assert chunks[0].id == chunk_document(parsed, words_per_chunk=2)[0].id
    assert evidence[0].chunk.text == "alpha conclusion."


def test_parse_rejects_empty_and_corrupt_pdf() -> None:
    with pytest.raises(DocumentParseError, match="empty"):
        parse_document("empty.txt", b"")
    with pytest.raises(DocumentParseError, match="corrupt"):
        parse_document("broken.pdf", b"not a pdf")


def test_context_fit_compression_and_classification() -> None:
    assert fits_context(100, 20, 200, margin=64)
    assert not fits_context(150, 20, 200, margin=64)
    history = [{"role": "user", "content": str(index)} for index in range(6)]
    compressed, notice = compress_history(history, lambda turns: "local summary", "confidential")
    assert notice is not None
    assert compressed[0]["label"] == "confidential"
    context = build_context(
        "what?", ["evidence"], [], tokenizer="fallback", reserved_output=10, context_limit=100
    )
    assert context.fits
    assert classify_task("Summarize this paper") == "summary"
    assert classify_task("Why does this work?") == "explain"
    assert classify_task("What is the result?") == "qa"


def test_document_session_upload_and_delete_isolation() -> None:
    init_db()
    db = SessionLocal()
    db.query(Chunk).delete()
    db.query(Document).delete()
    db.query(ChatSession).delete()
    db.query(RefreshToken).delete()
    db.query(User).delete()
    db.commit()
    db.close()
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/auth/register",
            json={"email": "doc-first@example.com", "password": "correct horse battery"},
        )
        headers = {"Authorization": f"Bearer {first.json()['access_token']}"}
        session = client.post("/api/v1/sessions", headers=headers).json()
        uploaded = client.post(
            f"/api/v1/sessions/{session['id']}/documents",
            headers=headers,
            files={"file": ("paper.txt", b"synthetic evidence", "text/plain")},
        )
        assert uploaded.status_code == 201
        other = client.post(
            "/api/v1/auth/register",
            json={"email": "doc-second@example.com", "password": "correct horse battery"},
        )
        other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
        assert (
            client.delete(f"/api/v1/sessions/{session['id']}", headers=other_headers).status_code
            == 404
        )
        assert (
            client.delete(f"/api/v1/sessions/{session['id']}", headers=headers).status_code == 204
        )


def test_purge_removes_expired_non_persistent_content() -> None:
    init_db()
    db = SessionLocal()
    user = User(email="purge@example.com", password_hash="synthetic")
    db.add(user)
    db.flush()
    from datetime import UTC, datetime, timedelta

    session = ChatSession(
        user_id=user.id,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        persist_opt_in=False,
    )
    db.add(session)
    db.flush()
    document = Document(
        session_id=session.id,
        filename="expired.txt",
        pages=1,
        bytes=3,
        text="old",
    )
    db.add(document)
    db.commit()
    assert purge_expired_sessions(db) == 1
    assert db.get(ChatSession, session.id) is None
