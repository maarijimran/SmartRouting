from collections.abc import Callable, Sequence
from typing import TypeVar

from app.adapters.base import AdapterError

T = TypeVar("T")


class RetryMetrics:
    def __init__(self) -> None:
        self.attempts: list[tuple[str, str]] = []

    def record(self, action: str, status: str) -> None:
        self.attempts.append((action, status))


def run_with_reentry(
    actions: Sequence[str],
    execute: Callable[[str], T],
    eligible: Callable[[str], bool],
    max_retries: int = 1,
    metrics: RetryMetrics | None = None,
) -> tuple[str, T]:
    attempts = 0
    for action in actions:
        if attempts >= max_retries + 1:
            break
        if not eligible(action):
            continue
        attempts += 1
        try:
            result = execute(action)
            if metrics:
                metrics.record(action, "ok")
            return action, result
        except AdapterError as exc:
            if metrics:
                metrics.record(action, exc.error_class)
            continue
    raise AdapterError("All eligible attempts failed", "exhausted_retries")
