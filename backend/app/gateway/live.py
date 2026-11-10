"""Non-chat, non-persistent generation used by the evaluation harness (admin key only).

Lives in ``gateway/`` so adapters are still never imported elsewhere. Evaluation items are
synthetic or public, so no privacy re-scan is required here; user keys are never used.
"""

import time
from dataclasses import dataclass

import httpx

from app.adapters.base import GenerationParams
from app.adapters.ollama import OllamaAdapter
from app.adapters.openai_compat import OpenAICompatAdapter


@dataclass(frozen=True)
class LiveResult:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    latency_ms: float
    ttft_ms: float | None


async def live_generate(
    *,
    kind: str,
    base_url: str,
    model_id: str,
    api_key: str | None,
    messages: list[dict[str, str]],
    max_tokens: int,
    context_limit: int,
    timeout_s: float = 120.0,
) -> LiveResult:
    client = httpx.AsyncClient(timeout=timeout_s)
    adapter = (
        OllamaAdapter(base_url, model_id, client)
        if kind == "local"
        else OpenAICompatAdapter(base_url, model_id, api_key or "", client)
    )
    started = time.perf_counter()
    ttft = None
    parts: list[str] = []
    usage = None
    try:
        params = GenerationParams(max_output_tokens=max_tokens, context_limit=context_limit)
        async for chunk in adapter.generate(messages, params):
            if chunk.text:
                if ttft is None:
                    ttft = (time.perf_counter() - started) * 1000
                parts.append(chunk.text)
            if chunk.done:
                usage = chunk.usage
    finally:
        await client.aclose()
    return LiveResult(
        "".join(parts),
        usage.input_tokens if usage else None,
        usage.output_tokens if usage else None,
        usage.cost_usd if usage else None,
        (time.perf_counter() - started) * 1000,
        ttft,
    )
