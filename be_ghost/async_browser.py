"""Async Be_Ghost — same surface as BeGhost but on playwright.async_api."""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator

from playwright.async_api import async_playwright, Page, BrowserContext, Browser, Playwright

from .browser import LITE_FLAGS, BLOCK_BY_DEFAULT, Response, CaptchaError

if TYPE_CHECKING:
    from .lite.browser import AsyncLiteBrowser as _AsyncLiteBrowser
from .fingerprint import random_profile, get_profile
from .humanize import AsyncHumanPage
from .retry import retry_async
from .stealth import STEALTH_JS


class AsyncBeGhost:
    """Async stealth browser. Mirrors BeGhost."""

    def __init__(
        self,
        stealth: bool = True,
        lite: bool = True,
        headless: bool = True,
        profile: str | None = None,
        proxy: str | None = None,
        proxy_pool: Any = None,
        block_resources: set[str] | None = None,
        extra_args: list[str] | None = None,
        timeout_ms: int = 30000,
        storage_state: str | None = None,
        auto_save_storage: bool = True,
        trace: str | None = None,
        har_record: str | None = None,
        har_replay: str | None = None,
        max_bytes: int | None = None,
        max_seconds: float | None = None,
        client_hints: dict[str, str] | None = None,
        mode: str = "auto",
    ) -> None:
        if mode not in ("auto", "lite", "full"):
            raise ValueError(f"mode must be auto/lite/full, got {mode!r}")
        self.mode = mode
        self._lite_browser: "_AsyncLiteBrowser | None" = None
        self.stealth = stealth
        self.lite = lite
        self.headless = headless
        self.profile_name = profile
        self.proxy = proxy
        self.proxy_pool = proxy_pool
        self.block_resources = block_resources if block_resources is not None else BLOCK_BY_DEFAULT
        self.extra_args = extra_args or []
        self.timeout_ms = timeout_ms
        self.storage_state = storage_state
        self.auto_save_storage = auto_save_storage
        self.trace = trace
        self.har_record = har_record
        self.har_replay = har_replay
        self.max_bytes = max_bytes
        self.max_seconds = max_seconds
        self.client_hints_override = client_hints

        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._profile: dict = {}
        self._last_ctx: BrowserContext | None = None
        self._current_proxy: str | None = None

    async def start(self) -> "AsyncBeGhost":
        if self._browser:
            return self
        self._profile = get_profile(self.profile_name) if self.profile_name else random_profile()
        self._pw = await async_playwright().start()
        args = LITE_FLAGS + self.extra_args if self.lite else list(self.extra_args)
        launch_kwargs: dict[str, Any] = {"headless": self.headless, "args": args}
        if self.proxy and not self.proxy_pool:
            launch_kwargs["proxy"] = {"server": self.proxy}
        self._browser = await self._pw.chromium.launch(**launch_kwargs)
        return self

    async def close(self) -> None:
        if self._lite_browser:
            try:
                await self._lite_browser.close()
            except Exception:
                pass
            self._lite_browser = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None

    async def __aenter__(self) -> "AsyncBeGhost":
        return await self.start()

    async def __aexit__(self, *_exc) -> None:
        await self.close()

    async def _new_context(self) -> BrowserContext:
        assert self._browser is not None, "call await .start() first"
        p = self._profile
        kwargs: dict[str, Any] = dict(
            user_agent=p["user_agent"],
            viewport=p["viewport"],
            screen=p["screen"],
            device_scale_factor=p["device_scale_factor"],
            locale=p["locale"],
            timezone_id=p["timezone"],
            ignore_https_errors=True,
            java_script_enabled=True,
            bypass_csp=True,
        )
        if self.storage_state and os.path.exists(self.storage_state):
            kwargs["storage_state"] = self.storage_state
        if self.har_record:
            kwargs["record_har_path"] = self.har_record
            kwargs["record_har_mode"] = "full"
        if self.proxy_pool is not None:
            try:
                self._current_proxy = self.proxy_pool.next()
                kwargs["proxy"] = {"server": self._current_proxy}
            except Exception:
                self._current_proxy = None

        ctx = await self._browser.new_context(**kwargs)
        ctx.set_default_timeout(self.timeout_ms)

        ch = self.client_hints_override or p.get("client_hints") or {}
        if ch:
            await ctx.set_extra_http_headers(ch)

        if self.har_replay:
            await ctx.route_from_har(self.har_replay, not_found="abort")

        if self.stealth:
            init = (
                f"window.__BG_LANGS__ = {json.dumps(p['languages'])};"
                f"window.__BG_CORES__ = {p['cores']};"
                f"window.__BG_MEM__ = {p['memory']};"
                f"window.__BG_PLATFORM__ = {json.dumps(p['platform'])};"
                f"window.__BG_GL_VENDOR__ = {json.dumps(p['gl_vendor'])};"
                f"window.__BG_GL_RENDERER__ = {json.dumps(p['gl_renderer'])};"
                f"window.__BG_CANVAS_SEED__ = {p.get('canvas_seed', 0.0000123)};"
                f"{STEALTH_JS}"
            )
            await ctx.add_init_script(init)

        if self.lite and self.block_resources:
            blocked = self.block_resources

            async def _route(route):
                if route.request.resource_type in blocked:
                    await route.abort()
                else:
                    await route.continue_()

            await ctx.route("**/*", _route)

        if self.max_bytes:
            counter = {"n": 0}
            limit = self.max_bytes

            async def _on_response(resp):
                try:
                    body = await resp.body()
                    counter["n"] += len(body)
                    if counter["n"] > limit:
                        await ctx.close()
                except Exception:
                    pass

            ctx.on("response", lambda r: asyncio.create_task(_on_response(r)))

        if self.trace:
            await ctx.tracing.start(screenshots=True, snapshots=True, sources=False)

        self._last_ctx = ctx
        return ctx

    async def _close_context(self, ctx: BrowserContext) -> None:
        if self.trace:
            try:
                await ctx.tracing.stop(path=self.trace)
            except Exception:
                pass
        if self.storage_state and self.auto_save_storage:
            try:
                await ctx.storage_state(path=self.storage_state)
            except Exception:
                pass
        try:
            await ctx.close()
        except Exception:
            pass

    async def _get_lite(self, url: str, **kwargs) -> Response:
        from .lite.browser import AsyncLiteBrowser
        if self._lite_browser is None:
            self._lite_browser = AsyncLiteBrowser(
                profile=self.profile_name, proxy=self.proxy, timeout_ms=self.timeout_ms,
            )
            await self._lite_browser.start()
            if not self._profile:
                self._profile = self._lite_browser.profile
        return await self._lite_browser.get(url, **kwargs)

    async def get(
        self,
        url: str,
        *,
        wait_until: str = "domcontentloaded",
        wait_for: str | None = None,
        headers: dict[str, str] | None = None,
        retries: int = 0,
        retry_on_captcha: bool = False,
        screenshot: str | None = None,
        pdf: str | None = None,
        mhtml: str | None = None,
        auto_http: bool = False,
        force: str | None = None,
    ) -> Response:
        chosen = force or self.mode
        needs_render = bool(screenshot or pdf or mhtml)
        if needs_render:
            chosen = "full"

        if chosen in ("auto", "lite"):
            try:
                from .lite.browser import needs_full_fallback
                r = await self._get_lite(
                    url, headers=headers, retries=retries,
                    retry_on_captcha=retry_on_captcha,
                )
                if chosen == "lite":
                    return r
                escalate, _reason = needs_full_fallback(r)
                if not escalate:
                    return r
            except ImportError:
                if chosen == "lite":
                    raise
            except Exception:
                if chosen == "lite":
                    raise

        if auto_http:
            try:
                from . import transport
                if transport.available():
                    # curl_cffi is sync; run in thread to keep async loop free.
                    res = await asyncio.to_thread(
                        transport.fetch, url, headers=headers, proxy=self.proxy or None,
                    )
                    if 200 <= res.status < 400 and res.text:
                        from .captcha import detect as _det
                        if not _det(res.text, res.headers, res.status):
                            return transport.to_response(res, url)
            except Exception:
                pass

        if not self._browser:
            await self.start()

        async def _do() -> Response:
            ctx = await self._new_context()
            proxy_used = self._current_proxy
            try:
                if headers:
                    await ctx.set_extra_http_headers(headers)
                page = await ctx.new_page()
                if self.max_seconds:
                    page.set_default_timeout(int(self.max_seconds * 1000))
                t0 = time.monotonic()
                resp = await page.goto(url, wait_until=wait_until)  # type: ignore[arg-type]
                if wait_for:
                    await page.wait_for_selector(wait_for)
                html = await page.content()
                elapsed = int((time.monotonic() - t0) * 1000)
                cookies = await ctx.cookies()
                if screenshot:
                    await page.screenshot(path=screenshot, full_page=True)
                if pdf:
                    await page.pdf(path=pdf)
                if mhtml:
                    cdp = await ctx.new_cdp_session(page)
                    snap = await cdp.send("Page.captureSnapshot", {"format": "mhtml"})
                    with open(mhtml, "w", encoding="utf-8") as f:
                        f.write(snap.get("data", ""))
                r = Response(
                    url=url,
                    status=resp.status if resp else 0,
                    headers=dict(resp.headers) if resp else {},
                    html=html,
                    cookies=cookies,
                    final_url=page.url,
                    elapsed_ms=elapsed,
                )
                if retry_on_captcha and r.captcha:
                    if self.proxy_pool and proxy_used:
                        self.proxy_pool.mark_failure(proxy_used)
                    raise CaptchaError(r.captcha)
                if self.proxy_pool and proxy_used:
                    self.proxy_pool.mark_success(proxy_used)
                return r
            except Exception:
                if self.proxy_pool and proxy_used:
                    self.proxy_pool.mark_failure(proxy_used)
                raise
            finally:
                await self._close_context(ctx)

        if retries > 0:
            return await retry_async(_do, attempts=retries + 1)
        return await _do()

    async def get_many(
        self,
        urls: list[str],
        *,
        concurrency: int = 5,
        return_exceptions: bool = True,
        **kwargs: Any,
    ) -> list[Response | BaseException]:
        if not self._browser:
            await self.start()
        sem = asyncio.Semaphore(concurrency)

        async def _bound(u: str):
            async with sem:
                return await self.get(u, **kwargs)

        return await asyncio.gather(*(_bound(u) for u in urls), return_exceptions=return_exceptions)

    @asynccontextmanager
    async def session(self, url: str | None = None, *, human: bool = False) -> AsyncIterator[Page | AsyncHumanPage]:
        if not self._browser:
            await self.start()
        ctx = await self._new_context()
        page = await ctx.new_page()
        try:
            if url:
                await page.goto(url)
            yield AsyncHumanPage(page) if human else page
        finally:
            await self._close_context(ctx)

    async def save_storage(self, path: str) -> None:
        if not self._last_ctx:
            raise RuntimeError("no active context — call await .get() or open a .session() first")
        await self._last_ctx.storage_state(path=path)

    @property
    def profile(self) -> dict:
        return dict(self._profile)
