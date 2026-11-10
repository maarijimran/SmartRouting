from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

_PASSWORD_HASHER = PasswordHasher()
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("Password must contain at least 10 characters")
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def create_access_token(
    subject: str,
    secret: str,
    expires_minutes: int = 15,
    role: str = "user",
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
        "type": "access",
        "role": role,
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def decode_access_token(token: str, secret: str) -> dict[str, Any]:
    payload = jwt.decode(token, secret, algorithms=[_ALGORITHM])
    if payload.get("type") != "access" or not payload.get("sub"):
        raise ValueError("Invalid access token")
    return payload


def generate_refresh_token() -> str:
    import secrets

    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return _PASSWORD_HASHER.hash(token)


def verify_refresh_token(token: str, token_hash: str) -> bool:
    return verify_password(token, token_hash)
