"""Small in-memory sliding-window rate limiter (per process; fine for a lab deployment)."""

import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.auth.deps import current_user

_HITS: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def reset() -> None:
    _HITS.clear()


def rate_limit(bucket: str, limit: Callable[[], int], window_s: float = 60.0):
    """FastAPI dependency: at most ``limit()`` calls per ``window_s`` per user and bucket."""

    def dependency(user: Annotated[dict[str, str], Depends(current_user)]) -> None:
        now = time.monotonic()
        hits = _HITS[(user["id"], bucket)]
        while hits and now - hits[0] > window_s:
            hits.popleft()
        if len(hits) >= limit():
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Rate limit reached for {bucket}; wait a moment and retry.",
                headers={"Retry-After": str(int(window_s))},
            )
        hits.append(now)

    return dependency
