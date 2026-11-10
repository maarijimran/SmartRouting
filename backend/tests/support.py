"""Shared helpers for API-level tests (fake providers only)."""

import json
from uuid import uuid4

from app.db.models import Model, ModelPrice, User
from app.db.session import SessionLocal, init_db
from app.main import app
from fastapi.testclient import TestClient

PASSWORD = "correct horse battery"


def client() -> TestClient:
    init_db()
    return TestClient(app)


def make_user(c: TestClient, role: str = "user") -> dict:
    email = f"{role}-{uuid4().hex[:8]}@example.com"
    c.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).one()
        user.role = role
        db.commit()
        user_id = user.id
    token = c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    return {"headers": {"Authorization": f"Bearer {token}"}, "id": user_id, "email": email}


def seed_models(enabled: set[str]) -> dict[str, str]:
    """Create the demo models/prices and enable exactly the given slugs. Returns slug -> id."""
    specs = {
        "local-demo": ("local", 4096, 512, 0.0, 0.0),
        "cloud-cheap-demo": ("cloud", 8192, 512, 0.15, 0.6),
        "cloud-strong-demo": ("cloud", 8192, 512, 3.0, 15.0),
    }
    ids = {}
    with SessionLocal() as db:
        for model in db.query(Model).all():
            model.enabled = model.slug in enabled
        for slug, (kind, ctx, out, p_in, p_out) in specs.items():
            row = db.query(Model).filter(Model.slug == slug).one_or_none()
            if row is None:
                row = Model(
                    slug=slug,
                    kind=kind,
                    provider="fake" if kind == "local" else "openrouter",
                    endpoint="http://fake",
                    context_limit=ctx,
                    max_output=out,
                )
                db.add(row)
                db.flush()
                if kind == "cloud":
                    db.add(
                        ModelPrice(
                            model_id=row.id,
                            input_per_mtok=p_in,
                            output_per_mtok=p_out,
                            source="test fixture",
                        )
                    )
            row.enabled = slug in enabled
            ids[slug] = row.id
        db.commit()
    return ids


def connect_cloud(c: TestClient, user: dict, ids: dict[str, str], budget: float | None = None):
    created = c.post(
        "/api/v1/connections",
        headers=user["headers"],
        json={
            "provider": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "label": "test",
            "api_key": "sk-or-test-key-1234567890",
            **({"monthly_budget_usd": budget} if budget is not None else {}),
        },
    ).json()
    response = c.put(
        "/api/v1/models/preferences",
        headers=user["headers"],
        json=[
            {"model_id": ids["cloud-cheap-demo"], "connection_id": created["id"], "tier": "cheap"},
            {
                "model_id": ids["cloud-strong-demo"],
                "connection_id": created["id"],
                "tier": "strong",
            },
        ],
    )
    assert response.status_code == 204, response.text
    return created["id"]


def new_session(c: TestClient, user: dict, mode: str = "local_only", label: str = "public") -> str:
    sid = c.post("/api/v1/sessions", headers=user["headers"]).json()["id"]
    r = c.patch(
        f"/api/v1/sessions/{sid}", headers=user["headers"], json={"mode": mode, "label": label}
    )
    assert r.status_code == 200, r.text
    return sid


def chat(c: TestClient, user: dict, sid: str, prompt: str, **extra) -> list[tuple[str, dict]]:
    response = c.post(
        f"/api/v1/sessions/{sid}/chat",
        headers=user["headers"],
        json={"prompt": prompt, **extra},
    )
    assert response.status_code == 200, response.text
    events = []
    for block in response.text.strip().split("\n\n"):
        lines = block.split("\n")
        events.append((lines[0][7:], json.loads(lines[1][6:])))
    return events


def types(events) -> list[str]:
    return [name for name, _ in events]


def last(events, name: str) -> dict:
    return [data for event, data in events if event == name][-1]
