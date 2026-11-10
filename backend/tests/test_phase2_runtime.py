import asyncio

import pytest
from app.adapters.base import AdapterError, GenerationParams
from app.adapters.fake import FakeAdapter, FakeScript
from app.gateway.budget import Budget
from app.gateway.egress import EgressBlocked, send, send_cloud
from app.gateway.retry import RetryMetrics, run_with_reentry
from app.keys.vault import seal_provider_key
from app.privacy.gate import GateResult
from app.registry.eligibility import eligible_for_dispatch
from app.registry.health import is_healthy, local_hardware_available
from app.registry.models import HealthState, ModelSpec, PriceSnapshot
from app.registry.pricing import estimate_cost


def test_fake_adapter_success_and_usage() -> None:
    async def collect():
        return [chunk async for chunk in FakeAdapter().generate([], GenerationParams())]

    chunks = asyncio.run(collect())
    assert chunks[0].text == "fake response"
    assert chunks[-1].usage.output_tokens == 3


def test_fake_adapter_failure_is_normalized() -> None:
    async def collect():
        adapter = FakeAdapter(FakeScript(failure="timeout"))
        return [chunk async for chunk in adapter.generate([], GenerationParams())]

    with pytest.raises(AdapterError, match="timeout"):
        asyncio.run(collect())


def test_budget_hard_stop_and_settlement() -> None:
    budget = Budget(cap_usd=1.0)
    assert budget.reserve(0.75)
    assert not budget.reserve(0.30)
    budget.settle(0.75, 0.60)
    assert budget.spent_usd == 0.60
    assert budget.reserved_usd == 0


def test_pricing_health_and_hardware_checks() -> None:
    price = PriceSnapshot(1.0, 2.0, "2026-11-10", "pilot")
    assert estimate_cost(price, 1000, 500) == 0.002
    model = ModelSpec("local", "local", "ollama", 8192, 1024, min_ram_gb=16, min_vram_gb=8)
    assert local_hardware_available(model, 16, 8)
    assert not local_hardware_available(model, 8, 8)
    assert is_healthy(HealthState(ok=True))
    assert not is_healthy(HealthState(ok=False))


def test_retry_reenters_eligibility_before_fallback() -> None:
    calls = []
    metrics = RetryMetrics()

    def execute(action):
        calls.append(action)
        if action == "local":
            raise AdapterError("failed", "timeout")
        return "ok"

    action, result = run_with_reentry(
        ["local", "cloud"],
        execute,
        eligible=lambda action: action == "local" or (action == "cloud" and calls),
        max_retries=1,
        metrics=metrics,
    )
    assert action == "cloud"
    assert result == "ok"
    assert metrics.attempts == [("local", "timeout"), ("cloud", "ok")]


def test_egress_gate_blocks_before_adapter_call() -> None:
    async def collect():
        return [
            chunk async for chunk in send(FakeAdapter(), [], GenerationParams(), privacy_gate=False)
        ]

    with pytest.raises(EgressBlocked):
        asyncio.run(collect())


def test_egress_passes_allowed_request() -> None:
    async def collect():
        return [
            chunk async for chunk in send(FakeAdapter(), [], GenerationParams(), privacy_gate=True)
        ]

    chunks = asyncio.run(collect())
    assert chunks[-1].done


def test_cloud_egress_decrypts_only_at_dispatch() -> None:
    import base64

    captured = []
    master_key = base64.b64encode(b"3" * 32).decode()
    encrypted = seal_provider_key("provider-secret", master_key)

    def factory(api_key):
        captured.append(api_key)
        return FakeAdapter()

    async def collect():
        return [
            chunk
            async for chunk in send_cloud(
                factory,
                encrypted,
                master_key,
                [],
                GenerationParams(),
                privacy_gate=True,
                gate_result=GateResult(True, "eligible", "hash"),
            )
        ]

    chunks = asyncio.run(collect())
    assert chunks[-1].done
    assert captured == ["provider-secret"]


def test_unknown_cloud_price_is_ineligible() -> None:
    model = ModelSpec("cloud", "cloud", "openrouter", 8192, 1024)
    result = eligible_for_dispatch(
        model, None, HealthState(ok=True), input_tokens=10, reserved_output=10
    )
    assert not result.allowed
    assert result.reason == "price_unknown"
