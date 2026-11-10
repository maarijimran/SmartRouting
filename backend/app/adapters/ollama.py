import json
from collections.abc import AsyncIterator, Sequence

import httpx

from app.adapters.base import AdapterError, Chunk, GenerationParams, Usage


class OllamaAdapter:
    def __init__(self, base_url: str, model: str, client: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = client or httpx.AsyncClient()

    async def generate(
        self, messages: Sequence[dict[str, str]], params: GenerationParams
    ) -> AsyncIterator[Chunk]:
        payload = {
            "model": self.model,
            "messages": list(messages),
            "stream": params.stream,
            "options": {
                "num_ctx": params.context_limit,
                "temperature": params.temperature,
            },
        }
        try:
            if params.stream:
                async with self.client.stream(
                    "POST", f"{self.base_url}/api/chat", json=payload
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        body = json.loads(line)
                        text = body.get("message", {}).get("content", "")
                        if text:
                            yield Chunk(text=text)
                        if body.get("done"):
                            yield Chunk(
                                text="",
                                done=True,
                                usage=Usage(
                                    int(body.get("prompt_eval_count", 0)),
                                    int(body.get("eval_count", 0)),
                                    0.0,
                                ),
                            )
                return
            response = await self.client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AdapterError("Ollama request failed", "provider_error") from exc
        message = body.get("message", {})
        text = message.get("content", "")
        if not isinstance(text, str):
            raise AdapterError("Ollama returned invalid content", "invalid_response")
        yield Chunk(
            text=text,
            done=True,
            usage=Usage(
                int(body.get("prompt_eval_count", 0)),
                int(body.get("eval_count", 0)),
                0.0,
            ),
        )

    async def health(self) -> bool:
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            return response.is_success
        except httpx.HTTPError:
            return False

    def count_tokens(self, messages: Sequence[dict[str, str]]) -> int:
        return sum(len(message.get("content", "").split()) for message in messages)
