"""Context pool — pre-warm and reuse Playwright contexts.

A new Chromium context is ~50ms to create. For hundreds of small fetches,
that adds up. ContextPool keeps N contexts alive and rotates them.

Trade-off: pooled contexts share cookies between sequential users (we clear
cookies on release). For per-user isolation, use storage_state instead.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext
    from .browser import BeGhost


class ContextPool:
    def __init__(self, ghost: "BeGhost", size: int = 5, clear_cookies_on_release: bool = True) -> None:
        self.ghost = ghost
        self.size = max(1, size)
        self._idle: list["BrowserContext"] = []
        self._busy: int = 0
        self._lock = threading.Lock()
        self.clear_cookies_on_release = clear_cookies_on_release

    def acquire(self) -> "BrowserContext":
        with self._lock:
            if self._idle:
                self._busy += 1
                return self._idle.pop()
            if self._busy < self.size:
                self._busy += 1
                outside_lock = True
            else:
                outside_lock = False
        if outside_lock:
            return self.ghost._new_context()
        # All slots busy — fall back to a one-off context (won't be returned to pool).
        return self.ghost._new_context()

    def release(self, ctx: "BrowserContext") -> None:
        try:
            if self.clear_cookies_on_release:
                try:
                    ctx.clear_cookies()
                except Exception:
                    pass
            with self._lock:
                self._busy = max(0, self._busy - 1)
                if len(self._idle) < self.size:
                    self._idle.append(ctx)
                    return
            ctx.close()
        except Exception:
            try:
                ctx.close()
            except Exception:
                pass

    def close(self) -> None:
        with self._lock:
            ctxs = list(self._idle)
            self._idle.clear()
        for c in ctxs:
            try:
                c.close()
            except Exception:
                pass
