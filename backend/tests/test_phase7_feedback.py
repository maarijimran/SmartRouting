"""Reward math, scorers, feedback -> scored outcomes, rater blindness, analytics, retention."""

from datetime import UTC, datetime, timedelta

import app.gateway.service as service
import pytest
from app.adapters.fake import FakeAdapter, FakeScript
from app.analytics.queries import percentile
from app.db.models import (
    ChatSession,
    Message,
    RoutingAttempt,
    RoutingEvent,
    ScoredOutcome,
)
from app.db.session import SessionLocal
from app.documents.service import purge_old_metadata, run_retention
from app.feedback.agreement import cohen_kappa
from app.feedback.scoring import (
    automatic_score,
    exact_match,
    rubric_coverage,
    token_f1,
)
from app.routing.reward import RewardConfig, combine_quality, human_score, reward
from support import chat, client, last, make_user, new_session, seed_models

CFG = RewardConfig(c_ref_usd=0.01, l_ref_ms=10000)


# --- reward (worked examples) ------------------------------------------------
def test_human_score_bounds_and_worked_example():
    assert human_score(5, 5, 5, 5) == 1.0
    assert human_score(1, 1, 1, 1) == 0.0
    assert human_score(3, 3, 3, 3) == 0.5
    assert human_score(4, 4, 2, 2) == 0.5
    with pytest.raises(ValueError):
        human_score(0, 3, 3, 3)


def test_quality_combination_and_deferral():
    assert combine_quality(1.0, 0.5, CFG) == (pytest.approx(0.85), "both")
    assert combine_quality(0.8, None, CFG) == (0.8, "human")
    assert combine_quality(None, 0.4, CFG) == (0.4, "auto")
    assert combine_quality(None, None, CFG) == (None, None)  # defer


def test_reward_worked_example_matches_spec_formula():
    # Q=0.85, C=0.005 (half of C_ref), L=5000 (half of L_ref)
    # R = 0.5*0.85 + 0.3*0.5 + 0.2*0.5 = 0.675
    assert reward(0.85, 0.005, 5000, CFG) == pytest.approx(0.675)
    # costs above the references saturate rather than go negative
    assert reward(1.0, 1.0, 1e9, CFG) == pytest.approx(0.5)
    assert reward(0.0, 0.0, 0.0, CFG) == pytest.approx(0.5)


# --- scorers -------------------------------------------------------------------
def test_scorers_hand_computed():
    assert token_f1("the cat sat", "cat sat down") == pytest.approx(0.8)
    assert token_f1("completely different", "cat sat") == 0.0
    assert exact_match("The Cat!", "cat") == 1.0
    assert (
        rubric_coverage("we propose a transformer model for translation", ["transformer model"])
        == 1.0
    )
    assert rubric_coverage("nothing relevant", ["transformer model", "beam search"]) == 0.0
    assert automatic_score("qa", "cat sat", references=["cat sat"]) == 1.0
    assert automatic_score("qa", "anything") is None  # no reference -> defer


def test_kappa_known_values():
    assert cohen_kappa([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == 1.0
    # worked example: po=0.75, pe=0.5 -> 0.5 (unweighted)
    assert cohen_kappa([1, 1, 2, 2], [1, 1, 2, 1], weights="none") == pytest.approx(0.5)
    assert cohen_kappa([1, 1, 5, 5], [5, 5, 1, 1]) < 0


def test_percentile_matches_linear_interpolation():
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile([10], 0.95) == 10
    assert percentile([], 0.5) is None


# --- feedback -> scored outcomes ----------------------------------------------
def test_user_feedback_creates_scored_outcome_with_reward():
    with client() as c:
        user = make_user(c)
        seed_models({"local-demo"})
        sid = new_session(c, user)
        event_id = last(chat(c, user, sid, "Define entropy"), "done")["event_id"]
        # before feedback: deferred, no scored outcome
        with SessionLocal() as db:
            assert db.get(ScoredOutcome, event_id) is None
        r = c.post(
            f"/api/v1/events/{event_id}/feedback",
            headers=user["headers"],
            json={"correctness": 5, "relevance": 5, "completeness": 5, "usefulness": 5},
        )
        assert r.status_code == 201 and r.json()["scored"]
        with SessionLocal() as db:
            out = db.get(ScoredOutcome, event_id)
            event = db.get(RoutingEvent, event_id)
            assert out.q_source == "human" and out.quality == 1.0
            expected = reward(1.0, 0.0, event.generation_latency_ms)
            assert out.reward == pytest.approx(expected)
            assert out.usable_for_update  # public, no entities
        # other users cannot rate this event
        other = make_user(c)
        r2 = c.post(
            f"/api/v1/events/{event_id}/feedback",
            headers=other["headers"],
            json={"correctness": 1, "relevance": 1, "completeness": 1, "usefulness": 1},
        )
        assert r2.status_code == 404


def test_failed_selected_attempt_gets_minus_one_without_feedback():
    original = service.build_local_adapter
    service.build_local_adapter = lambda m, s: FakeAdapter(FakeScript(failure="timeout"))
    try:
        with client() as c:
            user = make_user(c)
            seed_models({"local-demo"})
            sid = new_session(c, user)
            events = chat(c, user, sid, "Define entropy")
            event_id = last(events, "error")["event_id"]
            with SessionLocal() as db:
                out = db.get(ScoredOutcome, event_id)
                assert out.reward == -1.0 and out.q_source == "failure"
    finally:
        service.build_local_adapter = original


def test_abstentions_and_sensitive_events_are_excluded_from_learning():
    with client() as c:
        user = make_user(c)
        seed_models({"cloud-cheap-demo"})  # no key -> abstain
        sid = new_session(c, user, mode="cloud_allowed")
        abstain = last(chat(c, user, sid, "Define entropy"), "abstain")
        with SessionLocal() as db:
            assert db.get(ScoredOutcome, abstain["event_id"]) is None
        seed_models({"local-demo"})
        sid2 = new_session(c, user)
        done = last(chat(c, user, sid2, "Mail me at canary.person@example.test"), "done")
        c.post(
            f"/api/v1/events/{done['event_id']}/feedback",
            headers=user["headers"],
            json={"correctness": 4, "relevance": 4, "completeness": 4, "usefulness": 4},
        )
        with SessionLocal() as db:
            out = db.get(ScoredOutcome, done["event_id"])
            assert out is not None and out.usable_for_update is False


# --- rater workflow ---------------------------------------------------------------
def test_blind_queue_leaks_no_model_info_and_agreement_report():
    with client() as c:
        admin = make_user(c, "admin")
        r1, r2, plain = make_user(c, "rater"), make_user(c, "rater"), make_user(c)
        h = admin["headers"]
        ids = [
            c.post(
                "/api/v1/rater/items",
                headers=h,
                json={
                    "prompt": f"question {i}",
                    "response": f"answer {i}",
                    "model": "secret-model-name",
                    "task_type": "qa",
                },
            ).json()["item_id"]
            for i in range(3)
        ]
        assert c.post("/api/v1/rater/assign", headers=h).status_code == 200
        queue = c.get("/api/v1/rater/queue", headers=r1["headers"])
        body = queue.text
        assert "secret-model-name" not in body and "model" not in body and "event_id" not in body
        mine = {i["item_id"] for i in queue.json()}
        assert mine and mine <= set(ids)
        assert c.get("/api/v1/rater/queue", headers=plain["headers"]).status_code == 403
        for item in c.get("/api/v1/rater/queue", headers=r1["headers"]).json():
            for score in (5, 4):
                c.post(
                    f"/api/v1/rater/{item['item_id']}/rating",
                    headers=r1["headers"],
                    json={
                        k: score for k in ("correctness", "relevance", "completeness", "usefulness")
                    },
                )
        for item in c.get("/api/v1/rater/queue", headers=r2["headers"]).json():
            c.post(
                f"/api/v1/rater/{item['item_id']}/rating",
                headers=r2["headers"],
                json={k: 5 for k in ("correctness", "relevance", "completeness", "usefulness")},
            )
        assert c.get("/api/v1/rater/queue", headers=r1["headers"]).json() == []
        report = c.get("/api/v1/rater/agreement", headers=h).json()
        assert report["items"] >= 1
        assert c.get("/api/v1/rater/agreement", headers=plain["headers"]).status_code == 403


# --- analytics (hand-computed fixtures) ---------------------------------------------
def test_analytics_aggregates_equal_hand_computed_values_and_scope_rules():
    with client() as c:
        user = make_user(c)
        seed_models({"local-demo"})
        sid = c.post("/api/v1/sessions", headers=user["headers"]).json()["id"]
        with SessionLocal() as db:
            for i, (cost, lat) in enumerate([(0.01, 100.0), (0.03, 300.0)]):
                db.add(
                    RoutingEvent(
                        user_id=user["id"],
                        session_id=sid,
                        policy_name="fixed_rules",
                        policy_version="0",
                        selected_model="local-demo",
                        status="succeeded",
                        measured_cost_usd=cost,
                        estimated_cost_usd=cost * 2,
                        generation_latency_ms=lat,
                        explanation="x",
                        task_type="qa",
                    )
                )
            db.add(
                RoutingEvent(
                    user_id=user["id"],
                    session_id=sid,
                    policy_name="fixed_rules",
                    policy_version="0",
                    status="abstained",
                    abstained=True,
                    abstain_reason="m:consent_required",
                    explanation="x",
                    task_type="qa",
                )
            )
            db.commit()
        s = c.get("/api/v1/analytics/summary", headers=user["headers"]).json()
        assert s["requests"] == 3 and s["answered"] == 2 and s["abstained"] == 1
        assert s["measured"]["total_cost_usd"] == pytest.approx(0.04)
        assert s["measured"]["mean_cost_usd"] == pytest.approx(0.02)
        assert s["estimated"]["mean_cost_usd"] == pytest.approx(0.04)  # separate series
        assert s["measured"]["latency_p50_ms"] == pytest.approx(200.0)
        assert s["abstention_rate"] == pytest.approx(1 / 3)
        assert s["local_share"] == 1.0
        privacy = c.get("/api/v1/analytics/privacy", headers=user["headers"]).json()
        assert privacy["abstain_reasons"] == {"consent_required": 1}
        assert (
            c.get("/api/v1/analytics/summary?scope=global", headers=user["headers"]).status_code
            == 403
        )
        admin = make_user(c, "admin")
        g = c.get("/api/v1/analytics/summary?scope=global", headers=admin["headers"])
        assert g.status_code == 200 and g.json()["requests"] >= 3
        mine = c.get("/api/v1/analytics/summary", headers=admin["headers"]).json()
        assert mine["requests"] == 0  # admin's own scope excludes other users' data
        assert c.get("/api/v1/export/events", headers=user["headers"]).status_code == 403
        exported = c.get("/api/v1/export/events?format=csv", headers=admin["headers"])
        assert exported.status_code == 200 and "selected_model" in exported.text.splitlines()[0]
        assert "question" not in exported.text  # metadata only


# --- retention -----------------------------------------------------------------------
def test_retention_purges_expired_sessions_and_old_metadata():
    with client() as c:
        user = make_user(c)
        seed_models({"local-demo"})
        sid = new_session(c, user)
        chat(c, user, sid, "Define entropy")
        old = datetime.now(UTC) - timedelta(days=45)
        with SessionLocal() as db:
            session = db.get(ChatSession, sid)
            session.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            event = db.query(RoutingEvent).filter_by(session_id=sid).first()
            event.created_at = old
            db.commit()
            event_id = event.id
            result = run_retention(db)
            assert result["sessions_purged"] >= 1 and result["events_purged"] >= 1
            assert db.query(Message).filter_by(session_id=sid).count() == 0
            assert db.get(RoutingEvent, event_id) is None
            assert db.query(RoutingAttempt).filter_by(event_id=event_id).count() == 0
            assert purge_old_metadata(db) == 0


def test_persist_opt_in_sessions_survive_purge_and_delete_my_data_wipes():
    with client() as c:
        user = make_user(c)
        seed_models({"local-demo"})
        sid = new_session(c, user)
        c.patch(f"/api/v1/sessions/{sid}", headers=user["headers"], json={"persist_opt_in": True})
        chat(c, user, sid, "Define entropy")
        with SessionLocal() as db:
            db.get(ChatSession, sid).expires_at = datetime.now(UTC) - timedelta(minutes=5)
            db.commit()
            run_retention(db)
            assert db.get(ChatSession, sid) is not None
        assert c.delete("/api/v1/me/data", headers=user["headers"]).status_code == 204
        with SessionLocal() as db:
            assert db.get(ChatSession, sid) is None
