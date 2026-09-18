"""In-process sliding-window rate limiting for the authentication endpoints.

Deliberately simple: a per-process dictionary of recent attempt timestamps.
That is enough to blunt credential stuffing against a single API instance and
adds no infrastructure.  Behind more than one worker or replica the limit
becomes per-worker, so a production deployment should move this to a shared
store — ``docs/guides/deployment.md`` records that as a required change rather
than leaving it implied.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.core.config import settings
from app.core.errors import RateLimitedError


class SlidingWindowLimiter:
    def __init__(self, max_attempts: int, window_seconds: float) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        """Record an attempt for ``key``; raise when the window is exhausted."""
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            cutoff = now - self.window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_attempts:
                retry_after = max(1.0, self.window_seconds - (now - bucket[0]))
                raise RateLimitedError(
                    f"Too many attempts. Try again in {int(retry_after)} seconds.",
                    retry_after=retry_after,
                )
            bucket.append(now)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


auth_limiter = SlidingWindowLimiter(
    settings.auth_rate_limit_attempts, settings.auth_rate_limit_window_seconds
)
