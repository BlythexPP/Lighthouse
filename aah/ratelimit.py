"""In-process per-IP sliding window. Disable with AAH_RATE_LIMIT_PER_MINUTE=0."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request

from aah.errors import AppError


def rate_key_for(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check_request(self, request: Request) -> None:
        self.check(rate_key_for(request))

    def check(self, key: str) -> None:
        if self.per_minute <= 0:
            return
        now = time.monotonic()
        window = 60.0
        queue = self._hits[key]
        while queue and now - queue[0] > window:
            queue.popleft()
        if len(queue) >= self.per_minute:
            retry_after = max(1, int(window - (now - queue[0])) + 1)
            raise AppError(
                429,
                "rate_limited",
                f"Rate limit exceeded. Retry after {retry_after} seconds.",
                details=[{"retry_after": retry_after}],
                headers={"Retry-After": str(retry_after)},
            )
        queue.append(now)
