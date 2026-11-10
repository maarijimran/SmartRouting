from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import current_user, require_role
from app.db.session import get_db
from app.feedback import service

router = APIRouter(prefix="/api/v1", tags=["feedback"])
Db = Annotated[Session, Depends(get_db)]
User = Annotated[dict[str, str], Depends(current_user)]
Rater = Annotated[dict[str, str], Depends(require_role("rater", "admin"))]
Admin = Annotated[dict[str, str], Depends(require_role("admin"))]


class Ratings(BaseModel):
    correctness: int = Field(ge=1, le=5)
    relevance: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    usefulness: int = Field(ge=1, le=5)


class ItemCreate(BaseModel):
    prompt: str = Field(min_length=1)
    response: str = Field(min_length=1)
    model: str = Field(min_length=1)
    task_type: str = "qa"
    evidence: str = ""
    event_id: str | None = None


def _outcome_json(outcome) -> dict:
    if outcome is None:
        return {"scored": False, "deferred": True}
    return {
        "scored": True,
        "reward": outcome.reward,
        "quality": outcome.quality,
        "q_source": outcome.q_source,
    }


@router.post("/events/{event_id}/feedback", status_code=status.HTTP_201_CREATED)
def submit_feedback(event_id: str, payload: Ratings, user: User, db: Db) -> dict:
    try:
        outcome = service.submit_user_feedback(db, user["id"], event_id, payload.model_dump())
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found") from exc
    return _outcome_json(outcome)


@router.get("/rater/queue")
def queue(rater: Rater, db: Db) -> list[dict]:
    return service.rater_queue(db, rater["id"])


@router.post("/rater/{item_id}/rating", status_code=status.HTTP_201_CREATED)
def rate(item_id: str, payload: Ratings, rater: Rater, db: Db) -> dict:
    try:
        service.submit_item_rating(db, rater["id"], item_id, payload.model_dump())
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No open assignment") from exc
    return {"ok": True}


@router.post("/rater/items", status_code=status.HTTP_201_CREATED)
def add_item(payload: ItemCreate, _: Admin, db: Db) -> dict:
    return {"item_id": service.create_item(db, **payload.model_dump()).id}


@router.post("/rater/enqueue-events")
def enqueue(_: Admin, db: Db, limit: int = 120) -> dict:
    return {"created": service.enqueue_events(db, limit)}


@router.post("/rater/assign")
def assign(_: Admin, db: Db, raters_per_item: int = 2) -> dict:
    try:
        return {"assigned_items": service.assign_items(db, raters_per_item)}
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/rater/agreement")
def agreement(_: Admin, db: Db) -> dict:
    return service.agreement_report(db)


@router.get("/rater/source-bias")
def source_bias(_: Admin, db: Db) -> dict:
    return service.source_bias_report(db)
