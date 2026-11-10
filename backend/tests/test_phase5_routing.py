import asyncio

from app.adapters.fake import FakeAdapter, FakeScript
from app.gateway.pipeline import PipelineCandidate, PipelineRequest, run_pipeline
from app.privacy.gate import GateResult
from app.registry.models import HealthState, ModelSpec, PriceSnapshot
from app.routing.eligibility import eligible_candidates
from app.routing.features import Features, estimate_candidate
from app.routing.rules import FixedRules, LocalOnly


def _features(**overrides):
    values = {
        "task": "definition",
        "input_tokens": 40,
        "evidence_chunks": 1,
        "evidence_spread": False,
        "mode": "balanced",
        "cost_preference": "balanced",
        "estimated_cost_usd": 0.0,
        "estimated_latency_ms": None,
        "retrieval_margin": 0.0,
    }
    values.update(overrides)
    return Features(**values)


def test_fixed_rules_are_explainable_and_local_first_for_simple_tasks():
    decision = FixedRules().select(_features(), ["local-demo", "cloud-cheap"])
    assert decision.action == "local-demo"
    assert decision.rule_id == "simple_task_local"
    assert decision.probability == 1.0


def test_eligibility_removes_unknown_price_and_privacy_block():
    cloud = ModelSpec("cloud-cheap", "cloud", "fake", 4096, 512)
    estimate = estimate_candidate(cloud, None, input_tokens=10, reserved_output=20)
    allowed, removed = eligible_candidates(
        [estimate],
        prices={"cloud-cheap": None},
        health={"cloud-cheap": HealthState(ok=True)},
        gates={"cloud-cheap": GateResult(True, "eligible", "hash")},
    )
    assert not allowed
    assert removed[0].reason == "price_unknown"


def test_pipeline_emits_route_tokens_and_done():
    candidate = PipelineCandidate(
        ModelSpec("local-demo", "local", "fake", 4096, 512),
        FakeAdapter(FakeScript(text="answer")),
        health=HealthState(ok=True),
    )
    request = PipelineRequest("question", [{"role": "user", "content": "question"}], _features())

    events = asyncio.run(_collect(request, [candidate]))
    assert [event.type for event in events] == ["route", "token", "done"]
    assert events[0].data["rule_id"] == "simple_task_local"
    assert events[-1].data["status"] == "succeeded"


def test_local_only_policy_rejects_cloud_selection():
    decision = LocalOnly().select(_features(mode="local_only"), ["local-demo"])
    assert decision.rule_id == "local_only_policy"


def test_pipeline_abstains_when_all_candidates_are_blocked():
    candidate = PipelineCandidate(
        ModelSpec("cloud-demo", "cloud", "fake", 4096, 512),
        FakeAdapter(),
        price=PriceSnapshot(1.0, 1.0, "now", "test"),
        health=HealthState(ok=True),
        gate=GateResult(False, "consent_required", "hash"),
    )
    request = PipelineRequest("question", [], _features(task="general"))
    events = asyncio.run(_collect(request, [candidate]))
    assert events[0].type == "abstain"
    assert events[0].data["removed"][0]["reason"] == "consent_required"


async def _collect(request, candidates):
    return [event async for event in run_pipeline(request, candidates)]
