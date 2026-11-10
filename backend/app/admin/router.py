from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.deps import current_user, require_role
from app.db.models import (
    ChatSession,
    Chunk,
    Document,
    Message,
    ProviderConnection,
    User,
)
from app.db.session import get_db
from app.documents.service import run_retention
from app.gateway.service import month_spend
from app.routing import policy_store

router = APIRouter(prefix="/api/v1", tags=["admin"])
Db = Annotated[Session, Depends(get_db)]
Admin = Annotated[dict[str, str], Depends(require_role("admin"))]
CurrentUser = Annotated[dict[str, str], Depends(current_user)]


class RolePatch(BaseModel):
    role: Literal["user", "rater", "admin"]


class ActivePatch(BaseModel):
    is_active: bool


def _policy_json(record) -> dict:
    return {
        "id": record.id,
        "name": record.name,
        "version": record.version,
        "kind": record.kind,
        "epsilon": record.epsilon,
        "parent_id": record.parent_id,
        "config_hash": record.config_hash,
        "active": record.active,
        "created_at": record.created_at.isoformat(),
    }


@router.get("/admin/users")
def list_users(_: Admin, db: Db) -> list[dict]:
    return [
        {"id": u.id, "email": u.email, "role": u.role, "is_active": u.is_active}
        for u in db.scalars(select(User).order_by(User.created_at))
    ]


@router.put("/admin/users/{user_id}/role")
def set_role(user_id: str, payload: RolePatch, admin: Admin, db: Db) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.id == admin["id"] and payload.role != "admin":
        raise HTTPException(status.HTTP_409_CONFLICT, "Admins cannot demote themselves")
    user.role = payload.role
    db.commit()
    return {"id": user.id, "role": user.role}


@router.put("/admin/users/{user_id}/active")
def set_active(user_id: str, payload: ActivePatch, admin: Admin, db: Db) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.id == admin["id"] and not payload.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Admins cannot disable themselves")
    user.is_active = payload.is_active
    db.commit()
    return {"id": user.id, "is_active": user.is_active}


@router.get("/policies")
def list_policies(_: Admin, db: Db) -> list[dict]:
    return [_policy_json(r) for r in policy_store.list_versions(db)]


@router.post("/policies/rollback")
def rollback_policy(_: Admin, db: Db) -> dict:
    return _policy_json(policy_store.rollback(db))


@router.post("/policies/{policy_id}/activate")
def activate_policy(policy_id: str, _: Admin, db: Db) -> dict:
    try:
        return _policy_json(policy_store.activate_version(db, policy_id))
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Policy version not found") from exc


@router.post("/policies/learn")
def learn_now(_: Admin, db: Db) -> dict:
    """Force a bandit refit from fresh scored outcomes (normally automatic every 50)."""
    from app.routing.learner import maybe_update

    record = maybe_update(db, force=True)
    return {"published": _policy_json(record) if record else None}


@router.post("/policies/check-rollback")
def check_rollback(_: Admin, db: Db) -> dict:
    from app.routing.learner import check_rollback_triggers

    return {"rolled_back_reason": check_rollback_triggers(db)}


@router.get("/admin/budgets")
def budgets(_: Admin, db: Db) -> list[dict]:
    """Per-connection cap and month-to-date spend. Keys are never included."""
    return [
        {
            "connection_id": c.id,
            "label": c.label,
            "last4": c.last4,
            "monthly_budget_usd": c.monthly_budget_usd,
            "month_spend_usd": month_spend(db, c.id),
        }
        for c in db.scalars(select(ProviderConnection))
    ]


@router.post("/admin/retention/run")
def retention(_: Admin, db: Db) -> dict:
    return run_retention(db)


@router.delete("/me/data", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_data(user: CurrentUser, db: Db) -> None:
    """Immediately wipe all of the caller's session content (messages, documents, chunks)."""
    session_ids = db.scalars(select(ChatSession.id).where(ChatSession.user_id == user["id"])).all()
    if not session_ids:
        return
    doc_ids = db.scalars(select(Document.id).where(Document.session_id.in_(session_ids))).all()
    if doc_ids:
        db.execute(delete(Chunk).where(Chunk.document_id.in_(doc_ids)))
        db.execute(delete(Document).where(Document.id.in_(doc_ids)))
    db.execute(delete(Message).where(Message.session_id.in_(session_ids)))
    db.execute(delete(ChatSession).where(ChatSession.id.in_(session_ids)))
    db.commit()
