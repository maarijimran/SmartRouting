import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from app.adapters.base import AdapterError, Chunk, GenerationParams, Usage


@dataclass(frozen=True)
class FakeScript:
    text: str = "fake response"
    input_tokens: int = 10
    output_tokens: int = 3
    cost_usd: float = 0.0
    delay_ms: int = 0
    failure: str | None = None
    empty: bool = False
    truncated: bool = False


class FakeAdapter:
    def __init__(self, script: FakeScript = FakeScript()) -> None:
        self.script = script

    async def generate(
        self, messages: Sequence[dict[str, str]], params: GenerationParams
    ) -> AsyncIterator[Chunk]:
        if self.script.delay_ms:
            await asyncio.sleep(self.script.delay_ms / 1000)
        if self.script.failure:
            raise AdapterError(self.script.failure, self.script.failure)
        if self.script.empty:
            yield Chunk(
                text="",
                done=True,
                usage=Usage(self.script.input_tokens, 0, self.script.cost_usd),
            )
            return
        text = self.script.text
        if self.script.truncated:
            text = text[: max(1, len(text) // 2)]
        yield Chunk(text=text, ttft_ms=float(self.script.delay_ms))
        yield Chunk(
            text="",
            done=True,
            usage=Usage(self.script.input_tokens, self.script.output_tokens, self.script.cost_usd),
        )

    async def health(self) -> bool:
        return self.script.failure is None

    def count_tokens(self, messages: Sequence[dict[str, str]]) -> int:
        return sum(len(message.get("content", "").split()) for message in messages)
