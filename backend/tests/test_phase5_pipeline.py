"""Pipeline behaviour on fake adapters: egress re-scan, fallback, no mid-stream switch."""

import asyncio
from dataclasses import replace

from app.adapters.base import GenerationParams
from app.adapters.fake import FakeAdapter, FakeScript
from app.gateway.egress import EgressBlocked, send
from app.gateway.pipeline import PipelineCandidate, PipelineRequest, run_pipeline
from app.privacy.detector import PrivacyScanner
from app.privacy.gate import GateResult, check_outbound
from app.registry.models import HealthState, ModelSpec, PriceSnapshot
from app.routing.features import Features
from app.routing.rules import Decision, FixedRules

PRICE = PriceSnapshot(1.0, 2.0, "2026-11-10", "test")


class CloudFake(FakeAdapter):
    kind = "cloud"


def features(**kw):
    base = dict(
        task="qa",
        input_tokens=50,
        evidence_chunks=1,
        evidence_spread=False,
        mode="cloud_allowed",
        cost_preference="balanced",
        estimated_cost_usd=0.0,
        estimated_latency_ms=None,
        retrieval_margin=0.0,
    )
    base.update(kw)
    return Features(**base)


def local(script=FakeScript(text="local answer"), slug="local-a"):
    return PipelineCandidate(
        ModelSpec(slug, "local", "fake", 4096, 512),
        FakeAdapter(script),
        health=HealthState(ok=True),
        tier="local",
    )


def cloud(script=FakeScript(text="cloud answer"), slug="cloud-cheap", tier="cheap", check=None):
    return PipelineCandidate(
        ModelSpec(slug, "cloud", "fake", 4096, 512),
        CloudFake(script),
        price=PRICE,
        health=HealthState(ok=True),
        gate=GateResult(True, "eligible", "h"),
        outbound_check=check or (lambda payload: GateResult(True, "eligible", "h")),
        tier=tier,
    )


def run(request, candidates, **kw):
    async def go():
        records = []
        events = [
            e
            async for e in run_pipeline(
                request, candidates, on_record=lambda k, d: records.append((k, d)), **kw
            )
        ]
        return events, records

    return asyncio.run(go())


def req(**kw):
    return PipelineRequest("q", [{"role": "user", "content": "q"}], features(**kw))


def test_cloud_adapter_without_outbound_check_is_refused():
    async def go():
        return [c async for c in send(CloudFake(), [], GenerationParams(), privacy_gate=True)]

    try:
        asyncio.run(go())
    except EgressBlocked as exc:
        assert exc.reason == "no_outbound_check"
    else:
        raise AssertionError("cloud send without re-scan must be blocked")


def test_egress_rescans_final_payload_and_blocks_canary():
    seen = []

    class Spy(CloudFake):
        async def generate(self, messages, params):
            seen.append(messages)
            async for chunk in super().generate(messages, params):
                yield chunk

    scanner = PrivacyScanner()

    def check(payload):
        return check_outbound(
            payload,
            scanner=scanner,
            mode="cloud_allowed",
            label="public",
            user_id="u",
            session_id="s",
            model_id="m",
        )

    canary = "reach me at canary.person@example.test"

    async def go():
        return [
            c
            async for c in send(
                Spy(),
                [{"role": "user", "content": canary}],
                GenerationParams(),
                privacy_gate=True,
                outbound_check=check,
            )
        ]

    try:
        asyncio.run(go())
    except EgressBlocked as exc:
        assert exc.reason == "consent_required"
    assert seen == []  # the spy sink never received the canary


def test_blocked_egress_falls_back_without_counting_as_model_failure():
    blocked = cloud(check=lambda p: GateResult(False, "consent_required", "h"))
    events, records = run(req(task="qa"), [blocked, local()], policy=_Always("cloud-cheap"))
    assert [e.type for e in events] == ["route", "token", "done"]
    assert events[-1].data["model"] == "local-a"
    statuses = [d["status"] for k, d in records if k == "attempt"]
    assert statuses == ["blocked", "ok"]


class _Always:
    name = "always"
    version = "t"

    def __init__(self, action):
        self.action = action

    def select(self, features, eligible):
        return Decision(self.action, 1.0, "always", "test", {self.action: 1.0})


def test_failure_before_tokens_falls_back_and_is_bounded():
    bad = local(FakeScript(failure="timeout"), slug="local-bad")
    good = cloud()
    events, records = run(req(), [bad, good], policy=_Always("local-bad"))
    assert events[-1].type == "done"
    assert events[-1].data["model"] == "cloud-cheap"
    assert events[-1].data["failures"][0]["status"] == "timeout"
    assert [d["attempt_no"] for k, d in records if k == "attempt"] == [1, 2]


def test_all_attempts_failing_yields_error_event():
    events, _ = run(
        req(),
        [local(FakeScript(failure="provider_error")), cloud(FakeScript(failure="timeout"))],
        policy=_Always("local-a"),
    )
    assert events[-1].type == "error"
    assert len(events[-1].data["failures"]) == 2


def test_empty_response_counts_as_failure_and_falls_back():
    events, records = run(
        req(), [local(FakeScript(empty=True)), cloud()], policy=_Always("local-a")
    )
    assert events[-1].data["model"] == "cloud-cheap"
    assert [d["status"] for k, d in records if k == "attempt"] == ["empty", "ok"]


def test_no_model_switch_after_tokens_were_streamed():
    class MidFail(FakeAdapter):
        async def generate(self, messages, params):
            from app.adapters.base import AdapterError, Chunk

            yield Chunk(text="partial ")
            raise AdapterError("dropped", "provider_error")

    broken = PipelineCandidate(
        ModelSpec("local-mid", "local", "fake", 4096, 512),
        MidFail(),
        health=HealthState(ok=True),
        tier="local",
    )
    events, _ = run(req(), [broken, cloud()], policy=_Always("local-mid"))
    types = [e.type for e in events]
    assert types == ["route", "token", "error"]  # cloud never tried mid-generation


def test_policy_choosing_ineligible_model_is_overridden():
    events, _ = run(req(), [local()], policy=_Always("cloud-not-there"))
    assert events[0].data["model"] == "local-a"
    assert events[0].data["rule_id"] == "policy_invalid_fallback"


def test_local_only_mode_with_blocked_cloud_never_reaches_cloud():
    blocked = replace(cloud(), gate=GateResult(False, "local_only_mode", "h"))
    events, records = run(req(mode="local_only"), [blocked, local()])
    assert events[0].data["model"] == "local-a"
    assert events[0].data["removed"][0] == {"model": "cloud-cheap", "reason": "local_only_mode"}
    assert all(d["model"] != "cloud-cheap" for k, d in records if k == "attempt")


def test_abstain_lists_consent_needed_for_ui():
    blocked = replace(
        cloud(),
        gate=GateResult(False, "consent_required", "a" * 64),
        meta={"preview": "reach me at [EMAIL]"},
    )
    events, _ = run(req(), [blocked])
    assert events[0].type == "abstain"
    needed = events[0].data["consent_needed"][0]
    assert needed["model"] == "cloud-cheap" and needed["payload_hash"] == "a" * 64
    assert needed["preview"] == "reach me at [EMAIL]"


def test_route_event_separates_estimated_from_measured():
    events, _ = run(req(), [cloud()], policy=FixedRules())
    route, done = events[0].data, events[-1].data
    assert "estimated_cost_usd" in route and "estimated_input_tokens" in route
    assert "measured_cost_usd" in done and "estimated_cost_usd" not in done


def test_fixed_rules_use_tiers_and_config():
    fr = FixedRules()
    f = features(task="qa", evidence_chunks=4, tiers={"c1": "cheap", "c2": "strong", "l": "local"})
    d = fr.select(f, ["l", "c1", "c2"])
    assert d.action == "c2" and d.rule_id == "distributed_evidence_strong"
    f = features(task="qa", tiers={"c1": "cheap", "c2": "strong", "l": "local"})
    assert fr.select(f, ["l", "c1", "c2"]).action == "c1"
    f = features(task="qa", input_tokens=9000, tiers={"c1": "cheap", "l": "local"})
    assert fr.select(f, ["l", "c1"]).rule_id == "context_exceeds_local"
    f = features(mode="local_only", tiers={"c1": "cheap", "l": "local"})
    assert fr.select(f, ["l", "c1"]).action == "l"
