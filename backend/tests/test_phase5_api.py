"""End-to-end chat flow through the real API with fake providers."""

import json
from datetime import UTC, datetime

import app.gateway.service as service
from app.db.models import BudgetLedger, PrivacyFinding, RoutingAttempt, RoutingEvent
from app.db.session import SessionLocal
from app.gateway.factory import FakeCloudAdapter
from support import (
    chat,
    client,
    connect_cloud,
    last,
    make_user,
    new_session,
    seed_models,
    types,
)

CANARY = "reach me at canary.person@example.test"


def test_local_only_never_reaches_cloud_even_with_pii():
    with client() as c:
        user = make_user(c)
        ids = seed_models({"local-demo", "cloud-cheap-demo", "cloud-strong-demo"})
        connect_cloud(c, user, ids)
        sid = new_session(c, user, mode="local_only")
        events = chat(c, user, sid, f"Define entropy. {CANARY}")
        route = last(events, "route")
        assert route["model"] == "local-demo"
        assert route["rule_id"] == "label_forbids_cloud"
        removed = {r["model"]: r["reason"] for r in route["removed"]}
        assert removed["cloud-cheap-demo"] == "local_only_mode"
        assert removed["cloud-strong-demo"] == "local_only_mode"
        done = last(events, "done")
        assert done["status"] == "succeeded" and done["event_id"]


def test_cloud_allowed_routes_and_persists_event_attempts_and_ledger():
    with client() as c:
        user = make_user(c)
        ids = seed_models({"cloud-cheap-demo", "cloud-strong-demo"})
        connect_cloud(c, user, ids)
        sid = new_session(c, user, mode="cloud_allowed")
        events = chat(c, user, sid, "Explain the method please", cost_preference="balanced")
        assert types(events)[0] == "context"
        assert "route" in types(events) and "token" in types(events)
        done = last(events, "done")
        route = last(events, "route")
        assert route["model"] == "cloud-cheap-demo"
        assert route["estimated_cost_usd"] is not None
        assert done["measured_cost_usd"] == 0.0001
        with SessionLocal() as db:
            event = db.get(RoutingEvent, done["event_id"])
            assert event.status == "succeeded" and event.user_id == user["id"]
            assert event.estimated_input_tokens and event.measured_input_tokens
            attempts = db.query(RoutingAttempt).filter_by(event_id=event.id).all()
            assert [a.status for a in attempts] == ["ok"]
            ledger = db.query(BudgetLedger).filter_by(event_id=event.id).one()
            assert ledger.usd == 0.0001 and ledger.connection_id
        messages = c.get(f"/api/v1/sessions/{sid}/messages", headers=user["headers"]).json()
        assert [m["role"] for m in messages] == ["user", "assistant"]
        assert messages[1]["route"]["measured"]["cost_usd"] == 0.0001
        assert messages[1]["route"]["estimated"]["cost_usd"] is not None


def test_pii_without_consent_abstains_then_scoped_consent_allows():
    spy: list = []

    class Spy(FakeCloudAdapter):
        async def generate(self, messages, params):
            spy.append(messages)
            async for chunk in super().generate(messages, params):
                yield chunk

    original = service.build_cloud_adapter
    service.build_cloud_adapter = lambda model, conn, settings: Spy()
    try:
        with client() as c:
            user = make_user(c)
            ids = seed_models({"cloud-cheap-demo", "cloud-strong-demo"})
            connect_cloud(c, user, ids)
            sid = new_session(c, user, mode="cloud_allowed")
            first = chat(c, user, sid, f"What is entropy? {CANARY}")
            review = last(first, "review")
            assert types(first)[-1] == "review"  # findings shown first; the user decides
            assert spy == []  # nothing sent to the cloud sink
            assert {"scope": "prompt", "entity_type": "email", "count": 1} in review["findings"]
            assert review["local_available"] is False
            needed = {n["model"]: n for n in review["cloud_options"]}
            assert "[EMAIL]" in needed["cloud-cheap-demo"]["preview"]
            assert CANARY.split()[-1] not in needed["cloud-cheap-demo"]["preview"]
            # consent for a different payload / model does not unlock
            wrong = c.post(
                "/api/v1/consents",
                headers=user["headers"],
                json={
                    "session_id": sid,
                    "destination_model_id": "cloud-cheap-demo",
                    "payload_hash": "0" * 64,
                },
            )
            assert wrong.status_code == 201
            again = chat(c, user, sid, f"What is entropy? {CANARY}", sensitive_choice="cloud")
            assert types(again)[-1] == "abstain"  # choosing cloud never bypasses consent
            assert spy == []
            # exact scoped consent unlocks that model only
            ok = c.post(
                "/api/v1/consents",
                headers=user["headers"],
                json={
                    "session_id": sid,
                    "destination_model_id": "cloud-cheap-demo",
                    "payload_hash": needed["cloud-cheap-demo"]["payload_hash"],
                },
            )
            assert ok.status_code == 201
            # the retry is byte-identical (abstained turns leave no history) so consent applies
            retry = chat(c, user, sid, f"What is entropy? {CANARY}", sensitive_choice="cloud")
            assert last(retry, "route")["model"] == "cloud-cheap-demo"
            assert types(retry)[-1] == "done"
            assert len(spy) == 1  # exactly one payload reached the cloud sink
            sent = json.dumps(spy[0])
            assert "canary.person@example.test" in sent  # consented content, only for this model
            removed = {r["model"]: r["reason"] for r in last(retry, "route")["removed"]}
            assert removed["cloud-strong-demo"] == "consent_required"  # NOT unlocked
    finally:
        service.build_cloud_adapter = original


def test_sensitive_review_lets_user_choose_local_or_cloud():
    spy: list = []

    class Spy(FakeCloudAdapter):
        async def generate(self, messages, params):
            spy.append(messages)
            async for chunk in super().generate(messages, params):
                yield chunk

    original = service.build_cloud_adapter
    service.build_cloud_adapter = lambda model, conn, settings: Spy()
    try:
        with client() as c:
            user = make_user(c)
            ids = seed_models({"local-demo", "cloud-cheap-demo", "cloud-strong-demo"})
            connect_cloud(c, user, ids)
            sid = new_session(c, user, mode="cloud_allowed")
            prompt = f"Explain the method. {CANARY}"
            review = last(chat(c, user, sid, prompt), "review")
            assert review["local_available"] is True and review["local_models"] == ["local-demo"]
            assert {o["model"] for o in review["cloud_options"]} == {
                "cloud-cheap-demo",
                "cloud-strong-demo",
            }
            # a review leaves no history, so the retry payload is byte-identical
            assert c.get(f"/api/v1/sessions/{sid}/messages", headers=user["headers"]).json() == []

            local = chat(c, user, sid, prompt, sensitive_choice="local")
            route = last(local, "route")
            assert route["model"] == "local-demo" and types(local)[-1] == "done"
            assert {r["reason"] for r in route["removed"]} == {"user_chose_local"}
            assert spy == []

            sid2 = new_session(c, user, mode="cloud_allowed")
            option = {
                o["model"]: o for o in last(chat(c, user, sid2, prompt), "review")["cloud_options"]
            }["cloud-strong-demo"]
            c.post(
                "/api/v1/consents",
                headers=user["headers"],
                json={
                    "session_id": sid2,
                    "destination_model_id": "cloud-strong-demo",
                    "payload_hash": option["payload_hash"],
                },
            )
            cloud = chat(c, user, sid2, prompt, sensitive_choice="cloud")
            route = last(cloud, "route")
            assert route["model"] == "cloud-strong-demo" and types(cloud)[-1] == "done"
            removed = {r["model"]: r["reason"] for r in route["removed"]}
            assert removed == {
                "local-demo": "user_chose_cloud",
                "cloud-cheap-demo": "consent_required",
            }
            assert len(spy) == 1
    finally:
        service.build_cloud_adapter = original


def test_no_review_without_sensitive_content_or_in_local_only_mode():
    with client() as c:
        user = make_user(c)
        ids = seed_models({"local-demo", "cloud-cheap-demo", "cloud-strong-demo"})
        connect_cloud(c, user, ids)
        public = chat(c, user, new_session(c, user, mode="cloud_allowed"), "Explain the method")
        assert "review" not in types(public) and types(public)[-1] == "done"
        local_only = chat(c, user, new_session(c, user), f"Explain. {CANARY}")
        assert "review" not in types(local_only)
        assert last(local_only, "route")["model"] == "local-demo"


def test_abstain_when_no_model_available_is_actionable_and_persisted():
    with client() as c:
        user = make_user(c)
        seed_models({"cloud-cheap-demo"})  # no key for this user, no local model
        sid = new_session(c, user, mode="cloud_allowed")
        events = chat(c, user, sid, "Define entropy")
        abstain = last(events, "abstain")
        assert abstain["removed"][0] == {"model": "cloud-cheap-demo", "reason": "no_provider_key"}
        assert "suggestion" in abstain
        with SessionLocal() as db:
            event = db.get(RoutingEvent, abstain["event_id"])
            assert event.abstained and event.status == "abstained"


def test_privacy_findings_store_types_and_counts_never_text():
    with client() as c:
        user = make_user(c)
        seed_models({"local-demo"})
        sid = new_session(c, user, mode="local_only")
        events = chat(c, user, sid, f"Question. {CANARY}")
        event_id = last(events, "done")["event_id"]
        with SessionLocal() as db:
            rows = db.query(PrivacyFinding).filter_by(event_id=event_id).all()
            assert any(r.entity_type == "email" and r.scope == "prompt" for r in rows)
            dump = " ".join(f"{r.scope}{r.entity_type}{r.count}" for r in rows)
            assert "canary" not in dump
            event = db.get(RoutingEvent, event_id)
            assert "canary" not in (event.features_json or "")
            assert "canary" not in event.explanation


def test_confidential_label_blocks_cloud_without_entities():
    with client() as c:
        user = make_user(c)
        ids = seed_models({"cloud-cheap-demo", "cloud-strong-demo"})
        connect_cloud(c, user, ids)
        sid = new_session(c, user, mode="cloud_allowed", label="confidential")
        events = chat(c, user, sid, "Summarise nothing sensitive here")
        assert types(events)[-1] == "review"  # the label alone needs the user's decision
        review = last(events, "review")
        assert review["label"] == "confidential" and review["findings"] == []
        chosen = chat(c, user, sid, "Summarise nothing sensitive here", sensitive_choice="cloud")
        assert types(chosen)[-1] == "abstain"
        reasons = {r["reason"] for r in last(chosen, "abstain")["removed"]}
        assert reasons == {"consent_required"}


def test_budget_hard_stop_removes_cloud_when_cap_exhausted():
    with client() as c:
        user = make_user(c)
        ids = seed_models({"cloud-cheap-demo", "cloud-strong-demo"})
        conn_id = connect_cloud(c, user, ids, budget=0.0001)
        with SessionLocal() as db:
            db.add(
                BudgetLedger(
                    connection_id=conn_id,
                    user_id=user["id"],
                    kind="settle",
                    usd=0.0001,
                    ts=datetime.now(UTC),
                )
            )
            db.commit()
        sid = new_session(c, user, mode="cloud_allowed")
        events = chat(c, user, sid, "Explain the method")
        assert types(events)[-1] == "abstain"
        assert {r["reason"] for r in last(events, "abstain")["removed"]} == {"over_budget"}


def test_cross_user_session_isolation():
    with client() as c:
        owner, other = make_user(c), make_user(c)
        seed_models({"local-demo"})
        sid = new_session(c, owner)
        r = c.post(f"/api/v1/sessions/{sid}/chat", headers=other["headers"], json={"prompt": "hi"})
        assert r.status_code == 404
        assert (
            c.get(f"/api/v1/sessions/{sid}/messages", headers=other["headers"]).status_code == 404
        )


def test_history_is_compressed_locally_with_notice_and_label_inheritance():
    with client() as c:
        user = make_user(c)
        seed_models({"local-demo"})
        sid = new_session(c, user, mode="local_only")
        for i in range(4):
            chat(c, user, sid, f"turn number {i}")
        events = chat(c, user, sid, "one more")
        notice = [d for n, d in events if n == "compression_notice"]
        assert notice and notice[0]["compressed_turns"] >= 1


def test_provider_key_never_appears_in_any_response():
    with client() as c:
        user = make_user(c)
        ids = seed_models({"cloud-cheap-demo", "cloud-strong-demo"})
        connect_cloud(c, user, ids)
        listing = c.get("/api/v1/connections", headers=user["headers"]).text
        assert "sk-or-test-key" not in listing and "1234567890" not in listing
        assert "7890" in listing  # only the masked last4
        sid = new_session(c, user, mode="cloud_allowed")
        stream = c.post(
            f"/api/v1/sessions/{sid}/chat", headers=user["headers"], json={"prompt": "Explain it"}
        ).text
        assert "sk-or-test-key" not in stream
