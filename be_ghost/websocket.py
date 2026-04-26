"""WebSocket helper with browser-grade TLS via curl_cffi.

Use:
    with ghost.ws("wss://stream.example.com/ws") as ws:
        ws.send("hello")
        for msg in ws:
            print(msg)
"""

from __future__ import annotations

from typing import Iterator


def connect(url: str, *, headers: dict[str, str] | None = None, impersonate: str | None = None,
            proxy: str | None = None, timeout: float = 30.0):
    """Open a WebSocket. Returns a curl_cffi WebSocket object."""
    try:
        from curl_cffi.requests import Session  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError(
            "curl_cffi not installed. install with: pip install 'be_ghost[lite]'"
        ) from e
    from .fingerprint import curl_impersonate_target
    sess = Session()
    if proxy:
        sess.proxies = {"http": proxy, "https": proxy}
    return sess.ws_connect(
        url,
        headers=headers or {},
        impersonate=impersonate or curl_impersonate_target(),
        timeout=timeout,
    )


class WebSocketSession:
    """Iterator-friendly wrapper around curl_cffi.WebSocket."""

    def __init__(self, ws) -> None:
        self._ws = ws

    def send(self, data: str | bytes) -> None:
        self._ws.send(data)

    def recv(self) -> str | bytes:
        return self._ws.recv()

    def __iter__(self) -> Iterator[str | bytes]:
        try:
            while True:
                yield self.recv()
        except Exception:
            return

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass

    def __enter__(self) -> "WebSocketSession":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
