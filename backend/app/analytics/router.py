import csv
import io
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics import queries
from app.auth.deps import current_user, require_role
from app.db.models import RoutingEvent
from app.db.session import get_db

router = APIRouter(prefix="/api/v1", tags=["analytics"])
Db = Annotated[Session, Depends(get_db)]
User = Annotated[dict[str, str], Depends(current_user)]
Admin = Annotated[dict[str, str], Depends(require_role("admin"))]


def _scope(user: dict[str, str], scope: str) -> str | None:
    """Users only ever see their own data; admins may ask for the global view."""
    if scope == "global":
        if user["role"] != "admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Global analytics are admin-only")
        return None
    return user["id"]


Scope = Literal["me", "global"]


@router.get("/analytics/summary")
def summary(user: User, db: Db, scope: Scope = "me") -> dict:
    return queries.summary(db, _scope(user, scope))


@router.get("/analytics/by-model")
def by_model(user: User, db: Db, scope: Scope = "me") -> list[dict]:
    return queries.by_model(db, _scope(user, scope))


@router.get("/analytics/by-task")
def by_task(user: User, db: Db, scope: Scope = "me") -> list[dict]:
    return queries.by_task(db, _scope(user, scope))


@router.get("/analytics/cost-latency")
def cost_latency(user: User, db: Db, scope: Scope = "me") -> list[dict]:
    return queries.cost_latency(db, _scope(user, scope))


@router.get("/analytics/privacy")
def privacy(user: User, db: Db, scope: Scope = "me") -> dict:
    return queries.privacy(db, _scope(user, scope))


_EXPORT_FIELDS = [
    "id",
    "created_at",
    "task_type",
    "selected_model",
    "policy_name",
    "policy_version",
    "rule_id",
    "status",
    "action_prob",
    "estimated_input_tokens",
    "measured_input_tokens",
    "estimated_cost_usd",
    "measured_cost_usd",
    "routing_latency_ms",
    "generation_latency_ms",
    "ttft_ms",
    "abstained",
    "effective_label",
]


@router.get("/export/events")
def export_events(_: Admin, db: Db, format: Literal["csv", "json"] = "json") -> Response:
    """Scrubbed metadata only: no prompt, document or response text is ever exported here."""
    rows = [
        {name: getattr(e, name) for name in _EXPORT_FIELDS}
        for e in db.scalars(select(RoutingEvent).order_by(RoutingEvent.created_at))
    ]
    if format == "json":
        return Response(json.dumps(rows, default=str), media_type="application/json")
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_EXPORT_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return Response(buffer.getvalue(), media_type="text/csv")
