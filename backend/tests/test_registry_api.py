import base64
import os
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path('test_registry.db').absolute()}"
os.environ["KEY_VAULT_MASTER_KEY"] = base64.b64encode(b"4" * 32).decode()

from app.db.models import Model, ProviderConnection, RefreshToken, User, UserModelPref
from app.db.session import SessionLocal, init_db
from app.main import app
from fastapi.testclient import TestClient


def _reset() -> None:
    init_db()
    db = SessionLocal()
    db.query(UserModelPref).delete()
    db.query(Model).delete()
    db.query(ProviderConnection).delete()
    db.query(RefreshToken).delete()
    db.query(User).delete()
    db.commit()
    db.close()


def test_admin_registry_price_and_user_preferences() -> None:
    _reset()
    with TestClient(app) as client:
        admin = client.post(
            "/api/v1/auth/register",
            json={"email": "registry@example.com", "password": "correct horse battery"},
        )
        admin_headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}
        created = client.post(
            "/api/v1/models",
            headers=admin_headers,
            json={
                "slug": "local-test",
                "kind": "local",
                "provider": "ollama",
                "endpoint": "http://ollama:11434",
                "context_limit": 8192,
                "max_output": 1024,
            },
        )
        assert created.status_code == 201
        model_id = created.json()["id"]
        priced = client.put(
            f"/api/v1/models/{model_id}/price",
            headers=admin_headers,
            json={"input_per_mtok": 0, "output_per_mtok": 0, "source": "test"},
        )
        assert priced.status_code == 200
        second = client.post(
            "/api/v1/models",
            headers=admin_headers,
            json={
                "slug": "cloud-test",
                "kind": "cloud",
                "provider": "openrouter",
                "endpoint": "https://example.test",
                "context_limit": 8192,
                "max_output": 1024,
            },
        )
        second_id = second.json()["id"]
        user = client.post(
            "/api/v1/auth/register",
            json={"email": "registry-user@example.com", "password": "correct horse battery"},
        )
        user_headers = {"Authorization": f"Bearer {user.json()['access_token']}"}
        assert client.get("/api/v1/models", headers=user_headers).status_code == 200
        assert (
            client.put(
                "/api/v1/models/preferences",
                headers=user_headers,
                json=[
                    {"model_id": model_id, "tier": "cheap"},
                    {"model_id": second_id, "tier": "strong"},
                ],
            ).status_code
            == 204
        )
