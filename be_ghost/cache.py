"""On-disk response cache. Skip the request if URL+headers was fetched recently.

Optional dep: `diskcache` (pip install be_ghost[cache]). Falls back to a tiny
in-process LRU when diskcache is missing.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import asdict


def _key(url: str, headers: dict[str, str] | None) -> str:
    payload = url + "\n" + json.dumps(headers or {}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class _MemoryCache:
    """Minimal TTL+LRU cache so DiskCache works without the diskcache library."""

    def __init__(self, max_size: int = 256) -> None:
        self._d: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self.max_size = max_size

    def get(self, k: str) -> dict | None:
        item = self._d.get(k)
        if not item:
            return None
        expire, value = item
        if expire < time.time():
            self._d.pop(k, None)
            return None
        self._d.move_to_end(k)
        return value

    def set(self, k: str, value: dict, ttl: float) -> None:
        self._d[k] = (time.time() + ttl, value)
        self._d.move_to_end(k)
        while len(self._d) > self.max_size:
            self._d.popitem(last=False)

    def clear(self) -> None:
        self._d.clear()


class DiskCache:
    """TTL-based response cache. Backed by `diskcache` when installed, else in-memory."""

    def __init__(self, directory: str = ".be_ghost_cache", ttl: int = 3600) -> None:
        self.ttl = ttl
        try:
            from diskcache import Cache  # type: ignore[import-not-found]
            self._backend = Cache(directory)
            self._kind = "disk"
        except ImportError:
            self._backend = _MemoryCache()
            self._kind = "memory"

    def get(self, url: str, headers: dict[str, str] | None = None):
        from .browser import Response
        k = _key(url, headers)
        data = self._backend.get(k)
        return Response(**data) if isinstance(data, dict) else None

    def set(self, url: str, headers: dict[str, str] | None, response) -> None:
        from .browser import Response
        if not isinstance(response, Response):
            return
        k = _key(url, headers)
        payload = asdict(response)
        if self._kind == "disk":
            self._backend.set(k, payload, expire=self.ttl)
        else:
            self._backend.set(k, payload, ttl=self.ttl)

    def clear(self) -> None:
        self._backend.clear()

    @property
    def kind(self) -> str:
        return self._kind
