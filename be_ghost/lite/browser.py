"""LiteBrowser — same .get() / .session() shape as BeGhost, but no Chromium.

This is the "ghost" mode: pure HTTP with Chrome-grade TLS, no rendering engine.
Use it directly, or let BeGhost(mode='auto') route to it for you.
"""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator

from ..browser import Response
from .client import AsyncLiteClient, LiteClient, LiteHttpResult
from .dom import AsyncLitePage, LitePage  # noqa: F401


def _to_response(http: LiteHttpResult, requested_url: str) -> Response:
    return Response(
        url=requested_url,
        status=http.status,
        headers=http.headers,
        html=http.text,
        cookies=http.cookies,
        final_url=http.final_url,
        elapsed_ms=http.elapsed_ms,
    )


def needs_full_fallback(r: Response) -> tuple[bool, str]:
    """Heuristic — true if we should escalate this response to Chromium.

    Returns (should_fallback, reason).
    """
    if r.status >= 400:
        return True, f"http {r.status}"
    if r.captcha:
        return True, f"captcha:{r.captcha.kind}"

    body = r.html.strip()
    if not body:
        return True, "empty body"

    # JSON / API response — not a fallback case.
    if body.startswith(("{", "[")) and "html" not in (r.headers.get("content-type", "").lower()):
        return False, "json"

    lower = body.lower()
    # Classic SPA shell: a root div + a script bundle, almost no real content.
    if "<noscript>" in lower and "enable javascript" in lower:
        return True, "noscript-required"

    # Crude "is this a near-empty shell?" check.
    # Strip <script>, <style>, <head>, count remaining text.
    import re
    stripped = re.sub(r"<(script|style|head|svg)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    visible = re.sub(r"\s+", " ", stripped).strip()
    # Real pages with very little text (example.com has ~120 chars) shouldn't
    # escalate just on size. Require both a tiny body AND signs of an SPA shell
    # (a #root / #app / #__next mount point).
    if len(visible) < 100 and re.search(r'<div\s+[^>]*\b(id|class)\s*=\s*["\']?(root|app|__next|main)\b', body, re.I):
        return True, f"sparse-body+spa-mount ({len(visible)} chars visible)"

    return False, "ok"


class LiteBrowser:
    """No-Chromium browser: HTTP + selectolax + (optional) JS sandbox."""

    def __init__(
        self,
        profile: str | None = None,
        proxy: str | None = None,
        timeout_ms: int = 30000,
    ) -> None:
        self.profile_name = profile
        self.proxy = proxy
        self.timeout_ms = timeout_ms
        self._client: LiteClient | None = None

    def start(self) -> "LiteBrowser":
        if self._client is None:
            self._client = LiteClient(
                profile=self.profile_name, proxy=self.proxy, timeout=self.timeout_ms / 1000.0,
            )
            self._cached_profile = dict(self._client.profile)
        return self

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> "LiteBrowser":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.close()

    @property
    def profile(self) -> dict:
        if self._client:
            return dict(self._client.profile)
        return getattr(self, "_cached_profile", {})

    def get(
        self,
        url: str,
        *,
        wait_until: str = "domcontentloaded",  # accepted for compat, ignored
        wait_for: str | None = None,           # accepted for compat, ignored
        headers: dict[str, str] | None = None,
        retries: int = 0,
        retry_on_captcha: bool = False,
        screenshot: str | None = None,        # not supported in lite
        pdf: str | None = None,                # not supported in lite
        mhtml: str | None = None,              # not supported in lite
        auto_http: bool = True,                # always true here
    ) -> Response:
        if any([screenshot, pdf, mhtml]):
            raise NotImplementedError(
                "screenshot/pdf/mhtml require rendering — use BeGhost(mode='full')"
            )

        if not self._client:
            self.start()
        assert self._client is not None

        last_exc: BaseException | None = None
        for attempt in range(retries + 1):
            try:
                http = self._client.get(url, headers=headers)
                r = _to_response(http, url)
                if retry_on_captcha and r.captcha:
                    raise RuntimeError(f"captcha: {r.captcha.kind}")
                return r
            except Exception as e:
                last_exc = e
                if attempt < retries:
                    import time
                    import random
                    time.sleep(min(30.0, (2 ** attempt) * (1 + random.uniform(-0.3, 0.3))))
        assert last_exc is not None
        raise last_exc

    @contextmanager
    def session(self, url: str | None = None) -> Iterator[LitePage]:
        """Yield a stateful LitePage that follows links through the same session."""
        if not self._client:
            self.start()
        assert self._client is not None
        if url:
            http = self._client.get(url)
            page = LitePage(self._client, http.final_url, http.text, http)
        else:
            page = LitePage(self._client, "", "", None)
        try:
            yield page
        finally:
            pass  # client lifetime is managed by start/close


class AsyncLiteBrowser:
    """Async LiteBrowser. Mirrors the sync API."""

    def __init__(
        self,
        profile: str | None = None,
        proxy: str | None = None,
        timeout_ms: int = 30000,
    ) -> None:
        self.profile_name = profile
        self.proxy = proxy
        self.timeout_ms = timeout_ms
        self._client: AsyncLiteClient | None = None

    async def start(self) -> "AsyncLiteBrowser":
        if self._client is None:
            self._client = AsyncLiteClient(
                profile=self.profile_name, proxy=self.proxy, timeout=self.timeout_ms / 1000.0,
            )
            self._cached_profile = dict(self._client.profile)
        return self

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    async def __aenter__(self) -> "AsyncLiteBrowser":
        return await self.start()

    async def __aexit__(self, *_exc) -> None:
        await self.close()

    @property
    def profile(self) -> dict:
        if self._client:
            return dict(self._client.profile)
        return getattr(self, "_cached_profile", {})

    async def get(
        self,
        url: str,
        *,
        wait_until: str = "domcontentloaded",
        wait_for: str | None = None,
        headers: dict[str, str] | None = None,
        retries: int = 0,
        retry_on_captcha: bool = False,
        **_unsupported,
    ) -> Response:
        if not self._client:
            await self.start()
        assert self._client is not None

        last_exc: BaseException | None = None
        for attempt in range(retries + 1):
            try:
                http = await self._client.get(url, headers=headers)
                r = _to_response(http, url)
                if retry_on_captcha and r.captcha:
                    raise RuntimeError(f"captcha: {r.captcha.kind}")
                return r
            except Exception as e:
                last_exc = e
                if attempt < retries:
                    import asyncio
                    import random
                    await asyncio.sleep(min(30.0, (2 ** attempt) * (1 + random.uniform(-0.3, 0.3))))
        assert last_exc is not None
        raise last_exc

    async def get_many(
        self,
        urls: list[str],
        *,
        concurrency: int = 20,
        return_exceptions: bool = True,
        **kwargs,
    ) -> list[Response | BaseException]:
        import asyncio
        if not self._client:
            await self.start()
        sem = asyncio.Semaphore(concurrency)

        async def _bound(u: str):
            async with sem:
                return await self.get(u, **kwargs)

        return await asyncio.gather(*(_bound(u) for u in urls), return_exceptions=return_exceptions)

    @asynccontextmanager
    async def session(self, url: str | None = None) -> AsyncIterator["AsyncLitePage"]:
        """Yield a stateful AsyncLitePage that follows links through the same session."""
        from .dom import AsyncLitePage
        if not self._client:
            await self.start()
        assert self._client is not None
        if url:
            http = await self._client.get(url)
            page = AsyncLitePage(self._client, http.final_url, http.text, http)
        else:
            page = AsyncLitePage(self._client, "", "", None)
        try:
            yield page
        finally:
            pass
