import base64
import os
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path('test_auth.db').absolute()}"
os.environ["KEY_VAULT_MASTER_KEY"] = base64.b64encode(b"2" * 32).decode()

from app.db.models import ProviderConnection, RefreshToken, User
from app.db.session import SessionLocal, init_db
from app.main import app
from fastapi.testclient import TestClient


def test_register_login_me_and_connection_isolation() -> None:
    init_db()
    db = SessionLocal()
    db.query(ProviderConnection).delete()
    db.query(RefreshToken).delete()
    db.query(User).delete()
    db.commit()
    db.close()

    with TestClient(app) as client:
        first = client.post(
            "/api/v1/auth/register",
            json={"email": "first@example.com", "password": "correct horse battery"},
        )
        second = client.post(
            "/api/v1/auth/register",
            json={"email": "second@example.com", "password": "correct horse battery"},
        )
        assert first.status_code == 201
        assert second.status_code == 201
        assert client.get("/api/v1/auth/me").status_code == 401

        login = client.post(
            "/api/v1/auth/login",
            json={"email": "first@example.com", "password": "correct horse battery"},
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        me = client.get("/api/v1/auth/me", headers=headers)
        assert me.json()["email"] == "first@example.com"
        assert me.json()["role"] == "admin"

        created = client.post(
            "/api/v1/connections",
            headers=headers,
            json={
                "provider": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "label": "test",
                "api_key": "secret-provider-key",
            },
        )
        assert created.status_code == 201
        assert "secret-provider-key" not in created.text
        assert created.json()["last4"] == "-key"

        second_login = client.post(
            "/api/v1/auth/login",
            json={"email": "second@example.com", "password": "correct horse battery"},
        )
        second_headers = {"Authorization": f"Bearer {second_login.json()['access_token']}"}
        assert client.get("/api/v1/connections", headers=second_headers).json() == []


def test_refresh_rotates_and_rejects_reuse() -> None:
    init_db()
    db = SessionLocal()
    db.query(ProviderConnection).delete()
    db.query(RefreshToken).delete()
    db.query(User).delete()
    db.commit()
    db.close()

    with TestClient(app) as client:
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": "rotate@example.com", "password": "correct horse battery"},
        )
        old_cookie = registered.cookies.get("refresh_token")
        refreshed = client.post("/api/v1/auth/refresh", cookies={"refresh_token": old_cookie})
        assert refreshed.status_code == 200
        assert (
            client.post("/api/v1/auth/refresh", cookies={"refresh_token": old_cookie}).status_code
            == 401
        )


def test_lockout_password_change_and_connection_test() -> None:
    init_db()
    db = SessionLocal()
    db.query(ProviderConnection).delete()
    db.query(RefreshToken).delete()
    db.query(User).delete()
    db.commit()
    db.close()

    with TestClient(app) as client:
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": "secure@example.com", "password": "correct horse battery"},
        )
        token = registered.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        for _ in range(5):
            failed = client.post(
                "/api/v1/auth/login",
                json={"email": "secure@example.com", "password": "wrong password"},
            )
            assert failed.status_code == 401
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"email": "secure@example.com", "password": "correct horse battery"},
            ).status_code
            == 429
        )
        changed = client.post(
            "/api/v1/auth/password",
            headers=headers,
            json={
                "current_password": "correct horse battery",
                "new_password": "new correct battery",
            },
        )
        assert changed.status_code == 204
        connection = client.post(
            "/api/v1/connections",
            headers=headers,
            json={
                "provider": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "label": "test",
                "api_key": "secret-provider-key",
            },
        )
        tested = client.post(
            f"/api/v1/connections/{connection.json()['id']}/test",
            headers=headers,
        )
        assert tested.status_code == 200
        assert tested.json()["status"] == "ok"
