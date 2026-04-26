"""Proxy rotation pool with health checks and dead-marking.

A ProxyPool owns a list of proxy URLs, hands out a fresh one per request, and
demotes proxies that fail. Pass `BeGhost(proxy_pool=ProxyPool([...]))` and each
context will get a different proxy.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Iterable


@dataclass
class _Entry:
    url: str
    failures: int = 0
    dead_until: float = 0.0  # epoch seconds


class ProxyPool:
    def __init__(
        self,
        proxies: Iterable[str],
        *,
        max_failures: int = 3,
        cooldown_seconds: float = 300.0,
        strategy: str = "round_robin",  # or "random"
    ) -> None:
        self._entries: list[_Entry] = [_Entry(url=p) for p in proxies if p]
        if not self._entries:
            raise ValueError("ProxyPool requires at least one proxy")
        self._idx = 0
        self._lock = threading.Lock()
        self.max_failures = max_failures
        self.cooldown_seconds = cooldown_seconds
        self.strategy = strategy

    def __len__(self) -> int:
        return len(self._entries)

    def alive(self) -> list[str]:
        now = time.time()
        return [e.url for e in self._entries if e.dead_until <= now]

    def next(self) -> str:
        """Return the next live proxy. Raises if all are dead."""
        with self._lock:
            now = time.time()
            n = len(self._entries)
            for _ in range(n):
                if self.strategy == "random":
                    e = random.choice(self._entries)
                else:
                    e = self._entries[self._idx % n]
                    self._idx += 1
                if e.dead_until <= now:
                    return e.url
            raise RuntimeError("all proxies are in cooldown")

    def mark_failure(self, url: str) -> None:
        with self._lock:
            for e in self._entries:
                if e.url == url:
                    e.failures += 1
                    if e.failures >= self.max_failures:
                        e.dead_until = time.time() + self.cooldown_seconds
                        e.failures = 0
                    return

    def mark_success(self, url: str) -> None:
        with self._lock:
            for e in self._entries:
                if e.url == url:
                    e.failures = 0
                    return

    def health_check(self, test_url: str = "https://httpbin.org/ip", timeout: float = 5.0) -> dict[str, bool]:
        """Sync health check against test_url. Marks failures on the pool."""
        try:
            from . import transport
            if not transport.available():
                raise ImportError
        except ImportError as e:
            raise RuntimeError("health_check requires curl_cffi (pip install 'be_ghost[http]')") from e
        results: dict[str, bool] = {}
        for entry in list(self._entries):
            try:
                r = transport.fetch(test_url, proxy=entry.url, timeout=timeout)
                ok = 200 <= r.status < 400
            except Exception:
                ok = False
            results[entry.url] = ok
            if ok:
                self.mark_success(entry.url)
            else:
                self.mark_failure(entry.url)
        return results
