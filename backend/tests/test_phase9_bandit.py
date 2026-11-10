"""Bandit properties, versioning, shadow mode, rollback and the privacy-gate interlock."""

import json
import random
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from app.db.models import PolicyVersionRecord, RoutingEvent, ScoredOutcome
from app.db.session import SessionLocal
from app.routing import learner, policy_store
from app.routing.bandit import (
    DIM,
    EpsilonGreedyRidge,
    Outcome,
    Scaler,
    epsilon_at,
)
from app.routing.features import Features
from app.routing.frozen import FrozenRouter
from app.routing.policies import load_policies
from app.routing.rules import FixedRules
from support import chat, client, last, make_user, new_session, seed_models

MODELS = ["local-a", "cloud-cheap", "cloud-strong"]


def feats(**kw):
    base = dict(
        task="qa",
        input_tokens=200,
        evidence_chunks=2,
        evidence_spread=False,
        mode="cloud_allowed",
        cost_preference="balanced",
        estimated_cost_usd=0.0,
        estimated_latency_ms=None,
        retrieval_margin=1.0,
        tiers={"local-a": "local", "cloud-cheap": "cheap", "cloud-strong": "strong"},
    )
    base.update(kw)
    return Features(**base)


def outcomes_for(slug, n, reward_fn, rng):
    rows = []
    for _ in range(n):
        f = feats(input_tokens=rng.randint(50, 2000), evidence_tokens=rng.randint(10, 600))
        rows.append(Outcome(slug, f.to_log(), reward_fn(f)))
    return rows


def trained(seed=0, n=60, **kw):
    rng = random.Random(seed)
    policy = EpsilonGreedyRidge({}, {}, Scaler(), version="t", seed=seed, **kw)
    batch = (
        outcomes_for("local-a", n, lambda f: 0.4, rng)
        + outcomes_for("cloud-cheap", n, lambda f: 0.6, rng)
        + outcomes_for("cloud-strong", n, lambda f: 0.5, rng)
    )
    return policy.update(batch)


def test_epsilon_schedule_goes_from_010_to_002_over_1000_decisions():
    assert epsilon_at(0, 0.10, 0.02, 1000) == pytest.approx(0.10)
    assert epsilon_at(500, 0.10, 0.02, 1000) == pytest.approx(0.06)
    assert epsilon_at(1000, 0.10, 0.02, 1000) == pytest.approx(0.02)
    assert epsilon_at(5000, 0.10, 0.02, 1000) == pytest.approx(0.02)


def test_never_selects_an_ineligible_model_and_probabilities_sum_to_one():
    policy = trained()
    rng = random.Random(1)
    for _ in range(300):
        eligible = rng.sample(MODELS, rng.randint(1, 3))
        f = feats(input_tokens=rng.randint(10, 3000))
        decision = policy.select(f, eligible)
        assert decision.action in eligible
        assert sum(decision.distribution.values()) == pytest.approx(1.0)
        assert set(decision.distribution) == set(eligible)
        assert decision.probability == pytest.approx(decision.distribution[decision.action])


def test_logged_probability_matches_epsilon_greedy_formula():
    policy = trained()
    f = feats()
    best, probs = policy.distribution(f, MODELS)
    eps, k = policy.epsilon, len(MODELS)
    assert probs[best] == pytest.approx(eps / k + 1 - eps)
    assert all(p == pytest.approx(eps / k) for s, p in probs.items() if s != best)


def test_update_only_uses_selected_models_and_never_mutates_the_old_policy():
    policy = trained()
    before = {k: v.copy() for k, v in policy.thetas.items()}
    counts = dict(policy.counts)
    rng = random.Random(9)
    new = policy.update(outcomes_for("cloud-cheap", 20, lambda f: 0.1, rng))
    assert new is not policy
    for slug in before:  # old policy untouched
        assert np.array_equal(policy.thetas[slug], before[slug])
    assert policy.counts == counts
    assert not np.array_equal(new.thetas["cloud-cheap"], before["cloud-cheap"])
    assert np.array_equal(new.thetas["local-a"], before["local-a"])  # not selected -> unchanged
    assert np.array_equal(new.thetas["cloud-strong"], before["cloud-strong"])
    assert new.counts["cloud-cheap"] == counts["cloud-cheap"] + 20
    assert len(new.thetas["local-a"]) == DIM


def test_bandit_learns_to_prefer_the_higher_reward_model():
    policy = trained(epsilon_initial=0.0, epsilon_final=0.0)
    choices = {policy.select(feats(), MODELS).action for _ in range(20)}
    assert choices == {"cloud-cheap"}  # highest mean reward in the fixture


def test_selection_is_deterministic_for_a_given_seed():
    a, b = trained(seed=3), trained(seed=3)
    seq_a = [a.select(feats(input_tokens=i), MODELS).action for i in range(40)]
    seq_b = [b.select(feats(input_tokens=i), MODELS).action for i in range(40)]
    assert seq_a == seq_b


def test_cloud_exploration_is_disabled_when_privacy_gate_is_red():
    policy = trained(cloud_exploration=False, epsilon_initial=0.5, epsilon_final=0.5)
    f = feats()
    best, probs = policy.distribution(f, MODELS)
    assert sum(probs.values()) == pytest.approx(1.0)
    cloud_only = [s for s in MODELS if s != "local-a"]
    if best == "local-a":
        assert all(probs[s] == 0.0 for s in cloud_only)
    else:  # exploration mass goes only to the local model; clouds keep exploit mass at most
        assert probs["cloud-strong" if best != "cloud-strong" else "cloud-cheap"] == 0.0
    # with only cloud models eligible there is nothing local to explore -> pure exploit
    best2, probs2 = policy.distribution(f, cloud_only)
    assert probs2[best2] == pytest.approx(1.0)


def test_cold_start_not_ready_until_fifty_examples_per_model():
    rng = random.Random(0)
    policy = EpsilonGreedyRidge({}, {}, Scaler(), version="c", cold_start_min=50)
    policy = policy.update(outcomes_for("local-a", 49, lambda f: 0.3, rng))
    assert not policy.ready
    policy = policy.update(outcomes_for("local-a", 1, lambda f: 0.3, rng))
    assert policy.ready


def test_serialisation_roundtrip_is_exact():
    policy = trained()
    clone = EpsilonGreedyRidge.from_params(policy.to_params(), version="t")
    f = feats()
    for slug in MODELS:
        assert clone.predict(f, slug) == pytest.approx(policy.predict(f, slug))
    assert json.dumps(policy.to_params())  # JSON-safe


def test_frozen_router_is_argmax_and_update_is_noop():
    rng = random.Random(0)
    batch = outcomes_for("local-a", 40, lambda f: 0.2, rng) + outcomes_for(
        "cloud-strong", 40, lambda f: 0.9, rng
    )
    frozen = FrozenRouter.train(batch, version="f1")
    decision = frozen.select(feats(), ["local-a", "cloud-strong"])
    assert decision.action == "cloud-strong" and decision.probability == 1.0
    assert frozen.update(batch) is frozen
    assert decision.rule_id == "frozen_argmax"


# --- DB-backed: versions, rollback, shadow mode, learner ---------------------------


def _reset(db):
    db.query(ScoredOutcome).delete()
    db.query(PolicyVersionRecord).filter(PolicyVersionRecord.kind != "rules").delete()
    db.commit()
    rules = policy_store.ensure_rules_version(db)
    policy_store.activate_version(db, rules.id)


def _scored(db, slug, reward, n, label_features=None):
    for i in range(n):
        db.add(
            ScoredOutcome(
                event_id=f"{slug}-{reward}-{i}-{random.random()}",
                model=slug,
                quality=0.5,
                q_source="human",
                reward=reward,
                cost_usd=0.0,
                latency_ms=10.0,
                features_json=json.dumps((label_features or feats()).to_log()),
                usable_for_update=True,
                created_at=datetime.now(UTC) + timedelta(milliseconds=i),
            )
        )
    db.commit()


def test_learner_publishes_immutable_version_every_50_outcomes_and_consumes_them():
    with client(), SessionLocal() as db:
        _reset(db)
        _scored(db, "cloud-cheap", 0.7, 49)
        assert learner.maybe_update(db) is None  # below the batch size
        _scored(db, "cloud-cheap", 0.7, 1)
        first = learner.maybe_update(db)
        assert first is not None and first.kind == "bandit" and not first.active
        assert first.parent_id == policy_store.active_record(db).id
        assert db.query(ScoredOutcome).filter(ScoredOutcome.consumed_by.is_(None)).count() == 0
        assert learner.maybe_update(db) is None  # nothing fresh
        _scored(db, "local-a", 0.2, 50)
        second = learner.maybe_update(db)
        p1 = json.loads(first.params_json)["models"]
        p2 = json.loads(second.params_json)["models"]
        assert p2["cloud-cheap"]["theta"] == p1["cloud-cheap"]["theta"]  # unaffected model frozen
        assert p2["local-a"]["n"] == 50
        assert json.loads(first.params_json)["models"].keys() == {"cloud-cheap"}  # v1 unchanged


def test_rollback_restores_previous_behaviour_exactly():
    with client(), SessionLocal() as db:
        _reset(db)
        eligible = ["local-a", "cloud-cheap", "cloud-strong"]
        f = feats(evidence_chunks=4)
        before = [FixedRules().select(f, eligible).action for _ in range(5)]
        policy = trained()
        record = policy_store.publish_version(
            db,
            name="adaptive_bandit",
            kind="bandit",
            version="bandit-test",
            params=policy.to_params(),
            parent_id=policy_store.active_record(db).id,
            activate=True,
        )
        serving, shadow = load_policies(db)
        assert serving.name == "adaptive_bandit" and shadow is None
        restored = policy_store.rollback(db)
        assert restored.version == policy_store.RULES_VERSION and restored.id != record.id
        serving, _ = load_policies(db)
        assert serving.name == "fixed_rules"
        assert [serving.select(f, eligible).action for _ in range(5)] == before


def test_unready_learned_policy_runs_in_shadow_while_rules_serve():
    with client(), SessionLocal() as db:
        _reset(db)
        rng = random.Random(0)
        young = EpsilonGreedyRidge({}, {}, Scaler(), version="young", cold_start_min=50).update(
            outcomes_for("local-demo", 5, lambda f: 0.5, rng)
        )
        policy_store.publish_version(
            db,
            name="adaptive_bandit",
            kind="bandit",
            version="bandit-young",
            params=young.to_params(),
            parent_id=policy_store.active_record(db).id,
        )
        serving, shadow = load_policies(db)
        assert serving.name == "fixed_rules"
        assert shadow is not None and shadow.name == "adaptive_bandit"
    with client() as c:  # shadow decision is logged on the event, rules still serve
        user = make_user(c)
        seed_models({"local-demo"})
        sid = new_session(c, user)
        events = chat(c, user, sid, "Define entropy")
        route = last(events, "route")
        assert route["policy"] == "fixed_rules"
        assert route["shadow"]["policy"] == "adaptive_bandit"
        with SessionLocal() as db:
            event = db.get(RoutingEvent, last(events, "done")["event_id"])
            assert json.loads(event.shadow_json)["action"] == "local-demo"


def test_rollback_triggers_reward_drop_and_privacy_gate():
    import app.privacy.suite as suite

    with client(), SessionLocal() as db:
        _reset(db)
        sid = None
        # baseline: rules events with good reward
        for i in range(5):
            _scored_event(db, f"rb-{i}", "fixed_rules", "0", 0.9, sid)
        policy = trained()
        record = policy_store.publish_version(
            db,
            name="adaptive_bandit",
            kind="bandit",
            version="bandit-bad",
            params=policy.to_params(),
            parent_id=policy_store.active_record(db).id,
            activate=True,
        )
        for i in range(30):
            _scored_event(db, f"bad-{i}", "adaptive_bandit", record.version, 0.1, sid)
        assert learner.check_rollback_triggers(db) == "reward_drop"
        assert policy_store.active_record(db).version == policy_store.RULES_VERSION
        # privacy incident trigger
        policy_store.activate_version(db, record.id)
        original = suite.privacy_gate_green
        learner.privacy_gate_green = lambda: False
        try:
            assert learner.check_rollback_triggers(db) == "privacy_gate_red"
        finally:
            learner.privacy_gate_green = original


def _scored_event(db, event_id, policy, version, reward, sid):
    from app.db.models import ChatSession, User

    if sid is None:
        user = db.query(User).first()
        if user is None:
            raise RuntimeError("need a user")
        session = ChatSession(user_id=user.id, expires_at=datetime.now(UTC) + timedelta(hours=1))
        db.add(session)
        db.flush()
        sid = session.id
    db.add(
        RoutingEvent(
            id=event_id,
            session_id=sid,
            policy_name=policy,
            policy_version=version,
            selected_model="local-a",
            status="succeeded",
            explanation="x",
        )
    )
    db.add(
        ScoredOutcome(
            event_id=event_id,
            model="local-a",
            reward=reward,
            quality=0.5,
            usable_for_update=False,
            created_at=datetime.now(UTC),
        )
    )
    db.commit()
