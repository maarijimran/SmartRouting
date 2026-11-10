from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import current_user, require_role
from app.db.models import ChatSession, ConsentRecord, InstitutionalPolicyRecord
from app.db.session import get_db

router = APIRouter(prefix="/api/v1", tags=["privacy"])
Db = Annotated[Session, Depends(get_db)]
User = Annotated[dict[str, str], Depends(current_user)]
Admin = Annotated[dict[str, str], Depends(require_role("admin"))]


class ConsentRequest(BaseModel):
    session_id: str
    destination_model_id: str
    payload_hash: str = Field(min_length=64, max_length=64)
    expires_minutes: int = Field(default=60, gt=0, le=1440)


class ConsentResponse(BaseModel):
    id: str
    session_id: str
    destination_model_id: str
    payload_hash: str
    expires_at: datetime
    revoked_at: datetime | None


class InstitutionalPolicyRequest(BaseModel):
    allow_cloud: bool
    forbid_labels: list[str] = []


def _policy_response(record: InstitutionalPolicyRecord | None) -> dict:
    if record is None:
        return {"allow_cloud": True, "forbid_labels": []}
    return {
        "allow_cloud": record.allow_cloud,
        "forbid_labels": [item for item in record.forbid_labels.split(",") if item],
    }


@router.post("/consents", response_model=ConsentResponse, status_code=status.HTTP_201_CREATED)
def create_consent(payload: ConsentRequest, user: User, db: Db) -> ConsentRecord:
    owned = db.scalar(
        select(ChatSession.id).where(
            ChatSession.id == payload.session_id, ChatSession.user_id == user["id"]
        )
    )
    if owned is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    record = ConsentRecord(
        user_id=user["id"],
        session_id=payload.session_id,
        destination_model_id=payload.destination_model_id,
        payload_hash=payload.payload_hash,
        expires_at=datetime.now(UTC) + timedelta(minutes=payload.expires_minutes),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/consents", response_model=list[ConsentResponse])
def list_consents(user: User, db: Db) -> list[ConsentRecord]:
    return list(db.scalars(select(ConsentRecord).where(ConsentRecord.user_id == user["id"])))


@router.delete("/consents/{consent_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_consent(consent_id: str, user: User, db: Db) -> None:
    record = db.scalar(
        select(ConsentRecord).where(
            ConsentRecord.id == consent_id, ConsentRecord.user_id == user["id"]
        )
    )
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consent not found")
    record.revoked_at = datetime.now(UTC)
    db.commit()


@router.get("/institutional-policy")
def get_institutional_policy(user: User, db: Db) -> dict:
    return _policy_response(db.scalar(select(InstitutionalPolicyRecord)))


@router.put("/institutional-policy")
def update_institutional_policy(payload: InstitutionalPolicyRequest, admin: Admin, db: Db) -> dict:
    record = db.scalar(select(InstitutionalPolicyRecord))
    if record is None:
        record = InstitutionalPolicyRecord(updated_by=admin["id"])
        db.add(record)
    record.allow_cloud = payload.allow_cloud
    record.forbid_labels = ",".join(payload.forbid_labels)
    record.updated_by = admin["id"]
    record.updated_at = datetime.now(UTC)
    db.commit()
    return _policy_response(record)
