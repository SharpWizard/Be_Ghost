"""HTTP fallback transport using curl_cffi to spoof TLS/JA3 fingerprint.

Many "advanced" detectors (Cloudflare, Akamai) check the TLS handshake before
any JS runs. A regular Python `requests` or `httpx` call leaks Python's TLS
fingerprint regardless of how good the in-browser stealth is. curl_cffi runs
the real BoringSSL stack used by Chrome and produces an identical handshake.

Use this when you don't need JS execution (JSON APIs, static HTML). It is
~100x cheaper than a browser fetch.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .fingerprint import curl_impersonate_target

if TYPE_CHECKING:
    from .browser import Response


def available() -> bool:
    try:
        import curl_cffi  # noqa: F401
        return True
    except ImportError:
        return False


@dataclass
class HttpResult:
    status: int
    headers: dict
    text: str
    final_url: str
    elapsed_ms: int


def fetch(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    proxy: str | None = None,
    timeout: float = 30.0,
    impersonate: str | None = None,
    method: str = "GET",
    data: dict | str | bytes | None = None,
) -> HttpResult:
    """JA3-spoofed HTTP fetch. Raises ImportError if curl_cffi isn't installed."""
    try:
        from curl_cffi import requests as cc
    except ImportError as e:
        raise ImportError(
            "curl_cffi not installed. install with: pip install 'be_ghost[http]'"
        ) from e

    target = impersonate or curl_impersonate_target()
    t0 = time.monotonic()
    r = cc.request(
        method,
        url,
        headers=headers or {},
        cookies=cookies or {},
        proxies={"http": proxy, "https": proxy} if proxy else None,
        timeout=timeout,
        impersonate=target,
        data=data,
        allow_redirects=True,
    )
    return HttpResult(
        status=r.status_code,
        headers=dict(r.headers),
        text=r.text,
        final_url=str(r.url),
        elapsed_ms=int((time.monotonic() - t0) * 1000),
    )


def to_response(http: HttpResult, url: str) -> "Response":
    """Adapt an HttpResult into a be_ghost.Response so the API surface matches."""
    from .browser import Response
    return Response(
        url=url,
        status=http.status,
        headers=http.headers,
        html=http.text,
        cookies=[],
        final_url=http.final_url,
        elapsed_ms=http.elapsed_ms,
    )
