from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.auth.schemas import ProviderConnectionCreate, ProviderConnectionResponse
from app.core.config import get_settings
from app.db.models import ProviderConnection
from app.db.session import get_db
from app.gateway.connections import test_connection as probe_connection
from app.keys.vault import seal_provider_key

router = APIRouter(prefix="/api/v1/connections", tags=["connections"])
Db = Annotated[Session, Depends(get_db)]
User = Annotated[dict[str, str], Depends(current_user)]


@router.get("", response_model=list[ProviderConnectionResponse])
def list_connections(user: User, db: Db) -> list[ProviderConnection]:
    query = select(ProviderConnection).where(ProviderConnection.user_id == user["id"])
    return list(db.scalars(query))


@router.post("", response_model=ProviderConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_connection(payload: ProviderConnectionCreate, user: User, db: Db) -> ProviderConnection:
    master_key = get_settings().key_vault_master_key
    if not master_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Provider key vault is not configured",
        )
    encrypted = seal_provider_key(payload.api_key, master_key)
    connection = ProviderConnection(
        user_id=user["id"],
        provider=payload.provider,
        base_url=payload.base_url,
        label=payload.label,
        key_ciphertext=encrypted.ciphertext,
        key_nonce=encrypted.nonce,
        key_version=encrypted.key_version,
        last4=payload.api_key[-4:],
        monthly_budget_usd=payload.monthly_budget_usd,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(connection_id: str, user: User, db: Db) -> None:
    connection = db.scalar(
        select(ProviderConnection).where(
            ProviderConnection.id == connection_id,
            ProviderConnection.user_id == user["id"],
        )
    )
    if connection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
    db.delete(connection)
    db.commit()


@router.post("/{connection_id}/test", response_model=ProviderConnectionResponse)
def test_connection(connection_id: str, user: User, db: Db) -> ProviderConnection:
    connection = db.scalar(
        select(ProviderConnection).where(
            ProviderConnection.id == connection_id,
            ProviderConnection.user_id == user["id"],
        )
    )
    if connection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
    connection.status = probe_connection(connection)
    db.commit()
    db.refresh(connection)
    return connection
