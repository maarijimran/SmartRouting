from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.deps import current_user, require_role
from app.db.models import Model, ModelHealth, ModelPrice, UserModelPref
from app.db.session import get_db
from app.registry.schemas import (
    ModelCreate,
    ModelHealthResponse,
    ModelPatch,
    ModelPreferenceRequest,
    ModelPriceCreate,
    ModelPriceResponse,
    ModelResponse,
)

router = APIRouter(prefix="/api/v1/models", tags=["models"])
Db = Annotated[Session, Depends(get_db)]
Admin = Annotated[dict[str, str], Depends(require_role("admin"))]
User = Annotated[dict[str, str], Depends(current_user)]


@router.get("", response_model=list[ModelResponse])
def list_models(db: Db, user: User) -> list[Model]:
    return list(db.scalars(select(Model).where(Model.enabled.is_(True))))


@router.get("/catalog")
def catalog(db: Db, user: User, include_disabled: bool = False) -> list[dict]:
    """Models with their latest price snapshot and health (admins may include disabled ones)."""
    query = select(Model).order_by(Model.slug)
    if not (include_disabled and user["role"] == "admin"):
        query = query.where(Model.enabled.is_(True))
    result = []
    for model in db.scalars(query):
        price = db.scalar(
            select(ModelPrice)
            .where(ModelPrice.model_id == model.id)
            .order_by(ModelPrice.captured_at.desc())
            .limit(1)
        )
        health = db.scalar(
            select(ModelHealth)
            .where(ModelHealth.model_id == model.id)
            .order_by(ModelHealth.ts.desc())
            .limit(1)
        )
        result.append(
            {
                "id": model.id,
                "slug": model.slug,
                "kind": model.kind,
                "provider": model.provider,
                "provider_model": model.provider_model,
                "context_limit": model.context_limit,
                "max_output": model.max_output,
                "enabled": model.enabled,
                "price": {
                    "input_per_mtok": price.input_per_mtok,
                    "output_per_mtok": price.output_per_mtok,
                    "captured_at": price.captured_at.isoformat(),
                    "source": price.source,
                }
                if price
                else None,
                "health": {"ok": health.ok, "p50_ms": health.p50_ms, "ts": health.ts.isoformat()}
                if health
                else None,
            }
        )
    return result


@router.patch("/{model_id}", response_model=ModelResponse)
def patch_model(model_id: str, payload: ModelPatch, db: Db, _: Admin) -> Model:
    model = db.get(Model, model_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(model, field, value)
    db.commit()
    db.refresh(model)
    return model


@router.post("", response_model=ModelResponse, status_code=status.HTTP_201_CREATED)
def create_model(payload: ModelCreate, db: Db, _: Admin) -> Model:
    if db.scalar(select(Model).where(Model.slug == payload.slug)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Model slug already exists")
    model = Model(**payload.model_dump())
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


@router.put("/{model_id}/price", response_model=ModelPriceResponse)
def set_price(model_id: str, payload: ModelPriceCreate, db: Db, _: Admin) -> ModelPrice:
    if db.get(Model, model_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model not found")
    price = ModelPrice(model_id=model_id, **payload.model_dump())
    db.add(price)
    db.commit()
    db.refresh(price)
    return price


@router.get("/health", response_model=list[ModelHealthResponse])
def list_health(db: Db, user: User) -> list[ModelHealth]:
    return list(db.scalars(select(ModelHealth).order_by(ModelHealth.ts.desc())))


@router.put("/preferences", status_code=status.HTTP_204_NO_CONTENT)
def set_preferences(payload: list[ModelPreferenceRequest], db: Db, user: User) -> None:
    if {item.tier for item in payload} != {"cheap", "strong"}:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Choose one cheap and one strong model",
        )
    if len({item.model_id for item in payload}) != len(payload):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Cheap and strong preferences must use different models",
        )
    db.execute(delete(UserModelPref).where(UserModelPref.user_id == user["id"]))
    for item in payload:
        model = db.get(Model, item.model_id)
        if model is None or not model.enabled:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Model is unavailable")
        db.add(UserModelPref(user_id=user["id"], **item.model_dump()))
    db.commit()
