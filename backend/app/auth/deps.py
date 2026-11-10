from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.security import decode_access_token

_BEARER = HTTPBearer(auto_error=False)


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_BEARER)],
) -> dict[str, str]:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    try:
        payload = decode_access_token(credentials.credentials, get_settings().jwt_secret)
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid access token") from exc
    return {"id": str(payload["sub"]), "role": str(payload.get("role", "user"))}


def require_role(*roles: str) -> Callable:
    def dependency(user: Annotated[dict[str, str], Depends(current_user)]) -> dict[str, str]:
        if user["role"] not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return dependency
