import json
from collections.abc import AsyncIterator, Sequence

import httpx

from app.adapters.base import AdapterError, Chunk, GenerationParams, Usage


class OpenAICompatAdapter:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.client = client or httpx.AsyncClient()

    async def generate(
        self, messages: Sequence[dict[str, str]], params: GenerationParams
    ) -> AsyncIterator[Chunk]:
        payload = {
            "model": self.model,
            "messages": list(messages),
            "stream": params.stream,
            "max_tokens": params.max_output_tokens,
            "temperature": params.temperature,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            if params.stream:
                async with self.client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line or line == "data: [DONE]":
                            continue
                        if line.startswith("data: "):
                            line = line[6:]
                        body = json.loads(line)
                        choice = body.get("choices", [{}])[0]
                        text = choice.get("delta", {}).get("content", "")
                        if text:
                            yield Chunk(text=text)
                        if body.get("usage"):
                            usage = body["usage"]
                            yield Chunk(
                                text="",
                                done=True,
                                usage=Usage(
                                    int(usage.get("prompt_tokens", 0)),
                                    int(usage.get("completion_tokens", 0)),
                                    float(body.get("cost", 0.0)),
                                ),
                            )
                return
            response = await self.client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=headers
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AdapterError("OpenAI-compatible request failed", "provider_error") from exc
        choices = body.get("choices", [])
        if not choices or not isinstance(choices[0].get("message", {}).get("content"), str):
            raise AdapterError("Provider returned invalid content", "invalid_response")
        usage = body.get("usage", {})
        yield Chunk(
            text=choices[0]["message"]["content"],
            done=True,
            usage=Usage(
                int(usage.get("prompt_tokens", 0)),
                int(usage.get("completion_tokens", 0)),
                float(body.get("cost", 0.0)),
            ),
        )

    async def health(self) -> bool:
        try:
            response = await self.client.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            return response.is_success
        except httpx.HTTPError:
            return False

    def count_tokens(self, messages: Sequence[dict[str, str]]) -> int:
        return sum(len(message.get("content", "").split()) for message in messages)
