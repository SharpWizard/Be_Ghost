"""Per-domain token-bucket rate limiter.

Use:
    rl = RateLimiter(default_rps=2.0, per_domain={"api.fast.com": 10.0})
    rl.acquire(url)             # blocks until token available
    await rl.acquire_async(url) # async variant
"""

from __future__ import annotations

import asyncio
import threading
import time
from urllib.parse import urlparse


class _Bucket:
    __slots__ = ("rate", "burst", "tokens", "last")

    def __init__(self, rate: float, burst: float | None = None) -> None:
        self.rate = max(0.001, rate)
        self.burst = burst if burst is not None else max(1.0, rate)
        self.tokens = self.burst
        self.last = time.monotonic()

    def take(self) -> float:
        """Take 1 token. Return seconds the caller should sleep before proceeding."""
        now = time.monotonic()
        elapsed = now - self.last
        self.last = now
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return 0.0
        deficit = 1.0 - self.tokens
        self.tokens = 0.0
        return deficit / self.rate


class RateLimiter:
    """Token-bucket rate limiter, one bucket per host."""

    def __init__(
        self,
        default_rps: float | None = None,
        per_domain: dict[str, float] | None = None,
        per_domain_burst: dict[str, float] | None = None,
    ) -> None:
        self.default_rps = default_rps
        self.per_domain = per_domain or {}
        self.per_domain_burst = per_domain_burst or {}
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def _bucket_for(self, host: str) -> _Bucket | None:
        rate = self.per_domain.get(host, self.default_rps)
        if rate is None:
            return None
        with self._lock:
            b = self._buckets.get(host)
            if not b:
                b = _Bucket(rate, self.per_domain_burst.get(host))
                self._buckets[host] = b
            return b

    def _wait_seconds(self, url: str) -> float:
        host = urlparse(url).netloc
        if not host:
            return 0.0
        b = self._bucket_for(host)
        if b is None:
            return 0.0
        with self._lock:
            return b.take()

    def acquire(self, url: str) -> None:
        wait = self._wait_seconds(url)
        if wait > 0:
            time.sleep(wait)

    async def acquire_async(self, url: str) -> None:
        wait = self._wait_seconds(url)
        if wait > 0:
            await asyncio.sleep(wait)
