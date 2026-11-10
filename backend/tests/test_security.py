from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hashing_and_minimum_length() -> None:
    hashed = hash_password("correct horse battery")

    assert hashed != "correct horse battery"
    assert verify_password("correct horse battery", hashed)
    assert not verify_password("wrong password", hashed)
    with pytest.raises(ValueError):
        hash_password("short")


def test_access_token_contains_subject_and_expires() -> None:
    token = create_access_token("user-1", "test-secret")
    payload = decode_access_token(token, "test-secret")

    assert payload["sub"] == "user-1"
    assert payload["type"] == "access"
    assert payload["exp"] > datetime.now(UTC).timestamp()


def test_expired_access_token_is_rejected() -> None:
    token = jwt.encode(
        {"sub": "user-1", "type": "access", "exp": datetime.now(UTC) - timedelta(seconds=1)},
        "test-secret",
        algorithm="HS256",
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token, "test-secret")
