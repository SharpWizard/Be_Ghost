"""JSON-line structured logger. Used by BeGhost.enable_logging()."""

from __future__ import annotations

import json
import sys
import threading
import time
from typing import IO, Optional


class JsonLineLogger:
    def __init__(self, path: str | None = None, *, stream: Optional[IO[str]] = None) -> None:
        if path is None and stream is None:
            stream = sys.stderr
        self._path = path
        self._stream = stream
        self._lock = threading.Lock()
        self._fp: IO[str] | None = None
        if path:
            self._fp = open(path, "a", encoding="utf-8", buffering=1)

    def emit(self, event: str, **fields) -> None:
        line = {"ts": time.time(), "event": event}
        line.update(fields)
        try:
            payload = json.dumps(line, default=str, ensure_ascii=False)
        except Exception:
            payload = json.dumps({"ts": time.time(), "event": "log_error", "for": event})
        with self._lock:
            if self._fp:
                self._fp.write(payload + "\n")
            elif self._stream:
                self._stream.write(payload + "\n")
                self._stream.flush()

    def close(self) -> None:
        if self._fp:
            try:
                self._fp.close()
            except Exception:
                pass
            self._fp = None
