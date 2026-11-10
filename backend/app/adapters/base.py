from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GenerationParams:
    max_output_tokens: int = 1024
    temperature: float = 0.0
    context_limit: int = 8192
    stream: bool = True


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cost_usd: float


@dataclass(frozen=True)
class Chunk:
    text: str
    done: bool = False
    usage: Usage | None = None
    ttft_ms: float | None = None


class AdapterError(Exception):
    """Normalized adapter failure with a retry classification."""

    def __init__(self, message: str, error_class: str = "provider_error") -> None:
        super().__init__(message)
        self.error_class = error_class


class Adapter(Protocol):
    async def generate(
        self, messages: Sequence[dict[str, str]], params: GenerationParams
    ) -> AsyncIterator[Chunk]: ...

    async def health(self) -> bool: ...

    def count_tokens(self, messages: Sequence[dict[str, str]]) -> int: ...
