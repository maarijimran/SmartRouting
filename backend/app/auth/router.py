from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Body, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
    verify_refresh_token,
)
from app.db.models import RefreshToken, User
from app.db.session import get_db

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
Db = Annotated[Session, Depends(get_db)]


def _is_locked(user: User, now: datetime) -> bool:
    if user.locked_until is None:
        return False
    locked_until = user.locked_until
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=UTC)
    return locked_until > now


def _issue_tokens(response: Response, db: Session, user: User, rotated_from: str | None = None):
    settings = get_settings()
    refresh_value = generate_refresh_token()
    record = RefreshToken(
        id=str(uuid4()),
        user_id=user.id,
        token_hash=hash_refresh_token(refresh_value),
        expires_at=datetime.now(UTC) + timedelta(days=7),
        rotated_from=rotated_from,
    )
    db.add(record)
    db.commit()
    response.set_cookie(
        "refresh_token",
        refresh_value,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=7 * 24 * 60 * 60,
    )
    return TokenResponse(
        access_token=create_access_token(user.id, settings.jwt_secret, role=user.role)
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, db: Db) -> TokenResponse:
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Account already exists")
    user = User(email=email, password_hash=hash_password(payload.password))
    if db.scalar(select(User.id)) is None or get_settings().admin_email.lower() == email:
        user.role = "admin"
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue_tokens(response, db, user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, db: Db) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    now = datetime.now(UTC)
    if user is not None and _is_locked(user, now):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Account temporarily locked")
    if user is None or not verify_password(payload.password, user.password_hash):
        if user is not None:
            user.failed_attempts += 1
            if user.failed_attempts >= 5:
                delay_minutes = min(60, 2 ** (user.failed_attempts - 5))
                user.locked_until = now + timedelta(minutes=delay_minutes)
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")
    user.failed_attempts = 0
    user.locked_until = None
    db.commit()
    return _issue_tokens(response, db, user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    response: Response,
    db: Db,
    payload: RefreshRequest | None = Body(default=None),
    cookie: str | None = Cookie(default=None, alias="refresh_token"),
) -> TokenResponse:
    token_value = (payload.refresh_token if payload else None) or cookie
    if not token_value:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token required")
    records = db.scalars(
        select(RefreshToken).where(
            RefreshToken.revoked_at.is_(None), RefreshToken.expires_at > datetime.now(UTC)
        )
    ).all()
    record = next(
        (item for item in records if verify_refresh_token(token_value, item.token_hash)),
        None,
    )
    if record is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    record.revoked_at = datetime.now(UTC)
    return _issue_tokens(response, db, record.user, rotated_from=record.id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response, user: Annotated[dict[str, str], Depends(current_user)], db: Db
) -> None:
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user["id"], RefreshToken.revoked_at.is_(None)
    ).update({RefreshToken.revoked_at: datetime.now(UTC)})
    db.commit()
    response.delete_cookie("refresh_token")


@router.get("/me", response_model=UserResponse)
def me(user: Annotated[dict[str, str], Depends(current_user)], db: Db) -> User:
    found = db.get(User, user["id"])
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return found


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    user: Annotated[dict[str, str], Depends(current_user)],
    db: Db,
) -> None:
    found = db.get(User, user["id"])
    if found is None or not verify_password(payload.current_password, found.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    found.password_hash = hash_password(payload.new_password)
    db.query(RefreshToken).filter(
        RefreshToken.user_id == found.id, RefreshToken.revoked_at.is_(None)
    ).update({RefreshToken.revoked_at: datetime.now(UTC)})
    db.commit()
