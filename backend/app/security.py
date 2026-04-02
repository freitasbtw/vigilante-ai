from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import Header, HTTPException, Request

from app.config import settings


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: dict[tuple[str, str], deque[float]] = {}

    def allow_request(self, *, client_id: str, route: str) -> bool:
        max_requests = settings.RATE_LIMIT_MAX_REQUESTS
        window_seconds = settings.RATE_LIMIT_WINDOW_SECONDS
        if max_requests <= 0 or window_seconds <= 0:
            return True

        now = time.monotonic()
        key = (client_id, route)
        cutoff = now - float(window_seconds)

        with self._lock:
            bucket = self._events.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= max_requests:
                return False
            bucket.append(now)
            return True

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


rate_limiter = InMemoryRateLimiter()


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    expected_key = settings.API_KEY.strip()
    if not expected_key:
        return
    if x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


def enforce_rate_limit(request: Request) -> None:
    client_id = request.client.host if request.client and request.client.host else "unknown"
    route = request.url.path
    if rate_limiter.allow_request(client_id=client_id, route=route):
        return
    raise HTTPException(
        status_code=429,
        detail="Rate limit exceeded. Try again later.",
        headers={"Retry-After": str(settings.RATE_LIMIT_WINDOW_SECONDS)},
    )
