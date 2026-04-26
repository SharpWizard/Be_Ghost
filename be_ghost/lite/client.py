"""Lite HTTP client: curl_cffi session with Chrome-perfect TLS / HTTP/2.

This is the network layer of LiteBrowser. It handles:
  - JA3/JA4 fingerprint matching (impersonate=chrome132)
  - HTTP/2 multiplexing
  - Persistent cookies via the session
  - Redirects, gzip/br
  - Sec-CH-UA Client Hints aligned with the profile

No Chromium, no Playwright. ~5 MB and ~20 MB RAM per session.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ..fingerprint import curl_impersonate_target, random_profile, get_profile


def available() -> bool:
    try:
        import curl_cffi  # noqa: F401
        return True
    except ImportError:
        return False


@dataclass
class LiteHttpResult:
    status: int
    headers: dict[str, str]
    text: str
    content: bytes
    final_url: str
    elapsed_ms: int
    cookies: list[dict]


class LiteClient:
    """Sync HTTP client with browser-grade TLS impersonation."""

    def __init__(
        self,
        profile: str | None = None,
        proxy: str | None = None,
        timeout: float = 30.0,
        impersonate: str | None = None,
        http_version: str | None = None,  # "h1", "h2", "h3", or None for default
    ) -> None:
        if not available():
            raise ImportError(
                "curl_cffi not installed. install with: pip install 'be_ghost[lite]'"
            )
        from curl_cffi.requests import Session  # type: ignore[import-not-found]

        self.profile = get_profile(profile) if profile else random_profile()
        self.timeout = timeout
        self.impersonate = impersonate or curl_impersonate_target()
        self.http_version = http_version
        self._session = Session()
        if proxy:
            self._session.proxies = {"http": proxy, "https": proxy}
        self._apply_default_headers()

    def _apply_default_headers(self) -> None:
        p = self.profile
        h = {"user-agent": p["user_agent"], "accept-language": p["locale"] + ",en;q=0.9"}
        h.update(p.get("client_hints") or {})
        self._session.headers.update(h)

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: Any = None,
        json: Any = None,
        timeout: float | None = None,
        allow_redirects: bool = True,
    ) -> LiteHttpResult:
        t0 = time.monotonic()
        kwargs = dict(
            headers=headers, data=data, json=json,
            timeout=timeout or self.timeout,
            allow_redirects=allow_redirects,
            impersonate=self.impersonate,
        )
        if self.http_version:
            kwargs["http_version"] = self.http_version
        r = self._session.request(method, url, **kwargs)
        elapsed = int((time.monotonic() - t0) * 1000)
        cookies = []
        try:
            for c in self._session.cookies.jar:
                cookies.append({
                    "name": c.name, "value": c.value,
                    "domain": c.domain, "path": c.path,
                    "secure": bool(c.secure), "expires": c.expires,
                })
        except Exception:
            pass
        return LiteHttpResult(
            status=r.status_code,
            headers=dict(r.headers),
            text=r.text,
            content=r.content,
            final_url=str(r.url),
            elapsed_ms=elapsed,
            cookies=cookies,
        )

    def get(self, url: str, **kw) -> LiteHttpResult:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw) -> LiteHttpResult:
        return self.request("POST", url, **kw)

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass

    def __enter__(self) -> "LiteClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


class AsyncLiteClient:
    """Async HTTP client. Uses curl_cffi.AsyncSession."""

    def __init__(
        self,
        profile: str | None = None,
        proxy: str | None = None,
        timeout: float = 30.0,
        impersonate: str | None = None,
    ) -> None:
        if not available():
            raise ImportError("curl_cffi not installed. install with: pip install 'be_ghost[lite]'")
        from curl_cffi.requests import AsyncSession  # type: ignore[import-not-found]

        self.profile = get_profile(profile) if profile else random_profile()
        self.timeout = timeout
        self.impersonate = impersonate or curl_impersonate_target()
        self._session = AsyncSession()
        if proxy:
            self._session.proxies = {"http": proxy, "https": proxy}
        p = self.profile
        h = {"user-agent": p["user_agent"], "accept-language": p["locale"] + ",en;q=0.9"}
        h.update(p.get("client_hints") or {})
        self._session.headers.update(h)

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: Any = None,
        json: Any = None,
        timeout: float | None = None,
        allow_redirects: bool = True,
    ) -> LiteHttpResult:
        t0 = time.monotonic()
        r = await self._session.request(
            method,
            url,
            headers=headers,
            data=data,
            json=json,
            timeout=timeout or self.timeout,
            allow_redirects=allow_redirects,
            impersonate=self.impersonate,
        )
        elapsed = int((time.monotonic() - t0) * 1000)
        cookies = []
        try:
            for c in self._session.cookies.jar:
                cookies.append({
                    "name": c.name, "value": c.value,
                    "domain": c.domain, "path": c.path,
                    "secure": bool(c.secure), "expires": c.expires,
                })
        except Exception:
            pass
        return LiteHttpResult(
            status=r.status_code,
            headers=dict(r.headers),
            text=r.text,
            content=r.content,
            final_url=str(r.url),
            elapsed_ms=elapsed,
            cookies=cookies,
        )

    async def get(self, url: str, **kw) -> LiteHttpResult:
        return await self.request("GET", url, **kw)

    async def post(self, url: str, **kw) -> LiteHttpResult:
        return await self.request("POST", url, **kw)

    async def close(self) -> None:
        try:
            await self._session.close()
        except Exception:
            pass

    async def __aenter__(self) -> "AsyncLiteClient":
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.close()
