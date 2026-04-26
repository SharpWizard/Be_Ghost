"""Be_Ghost — ultra-lightweight stealth browser on top of Playwright."""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterator

from playwright.sync_api import sync_playwright, BrowserContext, Browser, Playwright

if TYPE_CHECKING:
    from .lite.browser import LiteBrowser as _LiteBrowser
    from .pool import ContextPool as _ContextPool
    from .logging import JsonLineLogger as _JsonLineLogger

from .captcha import CaptchaInfo, detect as detect_captcha
from .fingerprint import random_profile, get_profile
from .humanize import HumanPage
from .retry import retry_sync
from .stealth import STEALTH_JS


# Chromium flags that strip memory, GPU, telemetry, and detection-friendly defaults.
LITE_FLAGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-breakpad",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-domain-reliability",
    "--disable-features=AudioServiceOutOfProcess,IsolateOrigins,site-per-process,Translate,BackForwardCache",
    "--disable-hang-monitor",
    "--disable-ipc-flooding-protection",
    "--disable-notifications",
    "--disable-popup-blocking",
    "--disable-print-preview",
    "--disable-prompt-on-repost",
    "--disable-renderer-backgrounding",
    "--disable-sync",
    "--metrics-recording-only",
    "--mute-audio",
    "--no-default-browser-check",
    "--no-first-run",
    "--no-pings",
    "--password-store=basic",
    "--use-mock-keychain",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",  # WebRTC IP leak prevention
]

BLOCK_BY_DEFAULT = {"image", "media", "font", "stylesheet"}


@dataclass
class Response:
    """HTTP-like response object returned by ghost.get()."""
    url: str
    status: int
    headers: dict[str, str]
    html: str
    cookies: list[dict[str, Any]]
    final_url: str
    elapsed_ms: int

    @property
    def text(self) -> str:
        return self.html

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 400

    def json(self) -> Any:
        return json.loads(self.html)

    @property
    def captcha(self) -> CaptchaInfo:
        return detect_captcha(self.html, self.headers, self.status)

    # -- HTML parsing helpers (require selectolax) --------------------------

    def _parser(self):
        try:
            from selectolax.parser import HTMLParser
        except ImportError as e:
            raise ImportError(
                "selectolax not installed. install with: pip install 'be_ghost[parse]'"
            ) from e
        return HTMLParser(self.html)

    def select(self, css: str) -> list:
        """Return list of selectolax Nodes matching the CSS selector."""
        return self._parser().css(css)

    def select_one(self, css: str):
        return self._parser().css_first(css)

    def select_text(self, css: str, separator: str = " ", strip: bool = True) -> list[str]:
        """Convenience: list of text content from each matching element."""
        out = [n.text(separator=separator, strip=strip) for n in self.select(css)]
        return [t for t in out if t]

    def select_attr(self, css: str, attr: str) -> list[str]:
        return [n.attributes.get(attr, "") for n in self.select(css) if n.attributes.get(attr)]

    def text_only(self) -> str:
        return self._parser().body.text(separator=" ", strip=True) if self._parser().body else ""

    def links(self) -> list[str]:
        return self.select_attr("a[href]", "href")

    def metadata(self):
        """Return a PageMetadata with title, description, OpenGraph, JSON-LD, etc."""
        from .metadata import extract
        return extract(self.html)

    def extract(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Apply an extraction template — see be_ghost.extract for spec format."""
        from .extract import extract_from_html
        return extract_from_html(self.html, spec, request_url=self.url)

    def diff(self, other: "Response", *, context: int = 3):
        """Return an HtmlDiff between this response and another."""
        from .diff import diff
        return diff(self.html, other.html, context=context)

    def __repr__(self) -> str:
        return f"<Response {self.status} {self.url} ({len(self.html)} bytes)>"


class CaptchaError(RuntimeError):
    """Raised when retry_on_captcha=True and a challenge page was returned."""

    def __init__(self, info: CaptchaInfo) -> None:
        super().__init__(f"captcha challenge: {info.kind} ({info.evidence})")
        self.info = info


class BeGhost:
    """Lightweight stealth browser.

    Key args (all optional):
        stealth, lite, headless, profile, proxy, proxy_pool, block_resources,
        extra_args, timeout_ms, storage_state, auto_save_storage,
        trace (path to .zip — wires Playwright tracing),
        har_record (path to .har — captures all traffic),
        har_replay (path to .har — serves from recording, no network),
        max_bytes (abort context if exceeded), max_seconds (kill on timeout),
        client_hints (override Sec-CH-UA headers).
    """

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
        mode: str = "auto",  # "auto" | "lite" | "full"
        cache: Any = None,            # DiskCache instance
        rate_limit: Any = None,       # RateLimiter instance
        pool_size: int = 0,           # >0 enables ContextPool
        auto_accept_consent: bool = False,  # auto-click cookie banners on session()
        debug_dir: str | None = None,       # save screenshot+HTML+log on get() error
    ) -> None:
        if mode not in ("auto", "lite", "full"):
            raise ValueError(f"mode must be auto/lite/full, got {mode!r}")
        self.mode = mode
        self.cache = cache
        self.rate_limit = rate_limit
        self.pool_size = pool_size
        self.auto_accept_consent = auto_accept_consent
        self.debug_dir = debug_dir
        self._pool: "_ContextPool | None" = None
        self._lite_browser: "_LiteBrowser | None" = None
        self._stats = {
            "total": 0, "lite": 0, "full": 0, "cache_hit": 0,
            "captcha": 0, "retry": 0, "error": 0,
        }
        self._logger: "_JsonLineLogger | None" = None
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

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> "BeGhost":
        if self._browser:
            return self
        self._profile = get_profile(self.profile_name) if self.profile_name else random_profile()
        self._pw = sync_playwright().start()
        args = LITE_FLAGS + self.extra_args if self.lite else list(self.extra_args)
        launch_kwargs: dict[str, Any] = {"headless": self.headless, "args": args}
        # Browser-level proxy only when no pool (pool rotates per context).
        if self.proxy and not self.proxy_pool:
            launch_kwargs["proxy"] = {"server": self.proxy}
        self._browser = self._pw.chromium.launch(**launch_kwargs)
        return self

    def close(self) -> None:
        if self._pool is not None:
            try:
                self._pool.close()
            except Exception:
                pass
            self._pool = None
        if self._lite_browser:
            try:
                self._lite_browser.close()
            except Exception:
                pass
            self._lite_browser = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._pw:
            self._pw.stop()
            self._pw = None

    def __enter__(self) -> "BeGhost":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.close()

    # -- context / page builders ---------------------------------------------

    def _new_context(self) -> BrowserContext:
        assert self._browser is not None, "call .start() first"
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

        ctx = self._browser.new_context(**kwargs)
        ctx.set_default_timeout(self.timeout_ms)

        # Sec-CH-UA Client Hints — important for advanced detectors.
        ch = self.client_hints_override or p.get("client_hints") or {}
        if ch:
            ctx.set_extra_http_headers(ch)

        if self.har_replay:
            ctx.route_from_har(self.har_replay, not_found="abort")

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
            ctx.add_init_script(init)

        if self.lite and self.block_resources:
            blocked = self.block_resources
            ctx.route("**/*", lambda route: (
                route.abort() if route.request.resource_type in blocked else route.continue_()
            ))

        # Resource budget: count response bytes; abort context on overrun.
        if self.max_bytes:
            counter = {"n": 0}
            limit = self.max_bytes

            def _on_response(resp):
                try:
                    body = resp.body()
                    counter["n"] += len(body)
                    if counter["n"] > limit:
                        ctx.close()
                except Exception:
                    pass

            ctx.on("response", _on_response)

        if self.trace:
            ctx.tracing.start(screenshots=True, snapshots=True, sources=False)

        self._last_ctx = ctx
        return ctx

    def _close_context(self, ctx: BrowserContext) -> None:
        if self.trace:
            try:
                ctx.tracing.stop(path=self.trace)
            except Exception:
                pass
        if self.storage_state and self.auto_save_storage:
            try:
                ctx.storage_state(path=self.storage_state)
            except Exception:
                pass
        try:
            ctx.close()
        except Exception:
            pass

    # -- public API ----------------------------------------------------------

    def _get_lite(self, url: str, **kwargs) -> Response:
        """Run the request through LiteBrowser (no Chromium)."""
        from .lite.browser import LiteBrowser
        if self._lite_browser is None:
            self._lite_browser = LiteBrowser(
                profile=self.profile_name, proxy=self.proxy, timeout_ms=self.timeout_ms,
            )
            self._lite_browser.start()
            # share the profile so .profile reports something coherent
            if not self._profile:
                self._profile = self._lite_browser.profile
        return self._lite_browser.get(url, **kwargs)

    def get(
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
        cache: bool = True,  # disable to bypass self.cache for this call
    ) -> Response:
        """One-shot navigation. Routes by self.mode (auto/lite/full)."""
        self._stats["total"] += 1

        if cache and self.cache is not None:
            cached = self.cache.get(url, headers)
            if cached is not None:
                self._stats["cache_hit"] += 1
                self._log("cache_hit", url=url)
                return cached

        if self.rate_limit is not None:
            self.rate_limit.acquire(url)

        chosen = force or self.mode
        needs_render = bool(screenshot or pdf or mhtml)
        if needs_render:
            chosen = "full"

        if chosen in ("auto", "lite"):
            try:
                from .lite.browser import needs_full_fallback
                r = self._get_lite(
                    url, headers=headers, retries=retries,
                    retry_on_captcha=retry_on_captcha,
                )
                if chosen == "lite":
                    self._stats["lite"] += 1
                    self._log("ok", url=url, engine="lite", status=r.status, ms=r.elapsed_ms)
                    if cache and self.cache is not None:
                        self.cache.set(url, headers, r)
                    return r
                escalate, _reason = needs_full_fallback(r)
                if not escalate:
                    self._stats["lite"] += 1
                    self._log("ok", url=url, engine="lite", status=r.status, ms=r.elapsed_ms)
                    if cache and self.cache is not None:
                        self.cache.set(url, headers, r)
                    return r
                self._log("escalate_to_full", url=url, reason=_reason)
                # fall through to full
            except ImportError:
                if chosen == "lite":
                    raise
                # auto and lite deps missing — try full
            except Exception:
                if chosen == "lite":
                    raise
                # auto: any lite failure → fall through to full

        # ---- Chromium path -------------------------------------------------
        if auto_http:
            try:
                from . import transport
                if transport.available():
                    res = transport.fetch(url, headers=headers, proxy=self.proxy or None)
                    if 200 <= res.status < 400 and res.text:
                        from .captcha import detect as _det
                        if not _det(res.text, res.headers, res.status):
                            return transport.to_response(res, url)
            except Exception:
                pass

        if not self._browser:
            self.start()

        # Lazily build the context pool when requested.
        if self.pool_size and self._pool is None:
            from .pool import ContextPool
            self._pool = ContextPool(self, size=self.pool_size)

        def _do() -> Response:
            if self._pool is not None:
                ctx = self._pool.acquire()
                pooled = True
            else:
                ctx = self._new_context()
                pooled = False
            proxy_used = self._current_proxy
            try:
                if headers:
                    ctx.set_extra_http_headers(headers)
                page = ctx.new_page()
                if self.max_seconds:
                    page.set_default_timeout(int(self.max_seconds * 1000))
                t0 = time.monotonic()
                resp = page.goto(url, wait_until=wait_until)  # type: ignore[arg-type]
                if wait_for:
                    page.wait_for_selector(wait_for)
                html = page.content()
                elapsed = int((time.monotonic() - t0) * 1000)
                cookies = ctx.cookies()
                if screenshot:
                    page.screenshot(path=screenshot, full_page=True)
                if pdf:
                    page.pdf(path=pdf)
                if mhtml:
                    cdp = ctx.new_cdp_session(page)
                    snap = cdp.send("Page.captureSnapshot", {"format": "mhtml"})
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
                    self._stats["captcha"] += 1
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
                if pooled and self._pool is not None:
                    self._pool.release(ctx)
                else:
                    self._close_context(ctx)

        try:
            r = retry_sync(_do, attempts=retries + 1) if retries > 0 else _do()
        except Exception as e:
            self._stats["error"] += 1
            self._log("error", url=url, error=type(e).__name__, msg=str(e))
            if self.debug_dir:
                self._dump_debug(url, e)
            raise
        self._stats["full"] += 1
        self._log("ok", url=url, engine="full", status=r.status, ms=r.elapsed_ms)
        if cache and self.cache is not None:
            self.cache.set(url, headers, r)
        return r

    def paginate(
        self,
        url: str,
        *,
        next_selector: str,
        max_pages: int = 20,
        click_selector: str | None = None,
        **get_kwargs: Any,
    ) -> Iterator[Response]:
        """Yield Response per page, following `next_selector` until missing or max_pages.

        If click_selector is set, click it instead of following the href (for SPA paginators).
        """
        if not self._browser:
            self.start()
        ctx = self._new_context()
        try:
            page = ctx.new_page()
            page.goto(url, wait_until=get_kwargs.get("wait_until", "domcontentloaded"))
            for _ in range(max_pages):
                html = page.content()
                yield Response(
                    url=page.url, status=200, headers={}, html=html,
                    cookies=ctx.cookies(), final_url=page.url, elapsed_ms=0,
                )
                target = page.locator(click_selector or next_selector).first
                if not target.count():
                    break
                try:
                    if click_selector:
                        target.click()
                    else:
                        href = target.get_attribute("href")
                        if not href:
                            break
                        page.goto(href)
                    page.wait_for_load_state("domcontentloaded")
                except Exception:
                    break
        finally:
            self._close_context(ctx)

    @contextmanager
    def session(self, url: str | None = None, *, human: bool = False, force: str | None = None) -> Iterator[Any]:
        """Interactive session.

        In mode='lite' (or force='lite'), yields a LitePage — supports navigation,
        text reads, locators, and form submits via clicks on <a>/<button>.
        In mode='full' (or force='full'), yields a Playwright Page (or HumanPage).
        In mode='auto', uses Chromium so all interactions work.
        """
        chosen = force or (self.mode if self.mode != "auto" else "full")
        if chosen == "lite":
            from .lite.browser import LiteBrowser
            if self._lite_browser is None:
                self._lite_browser = LiteBrowser(
                    profile=self.profile_name, proxy=self.proxy, timeout_ms=self.timeout_ms,
                )
                self._lite_browser.start()
            with self._lite_browser.session(url) as page:
                yield page
            return

        if not self._browser:
            self.start()
        ctx = self._new_context()
        full_page = ctx.new_page()
        try:
            if url:
                full_page.goto(url)
                if self.auto_accept_consent:
                    from .consent import accept
                    accept(full_page)
            yield HumanPage(full_page) if human else full_page
        finally:
            self._close_context(ctx)

    def save_storage(self, path: str) -> None:
        if not self._last_ctx:
            raise RuntimeError("no active context — call .get() or open a .session() first")
        self._last_ctx.storage_state(path=path)

    @property
    def profile(self) -> dict:
        return dict(self._profile)

    # -- observability -------------------------------------------------------

    def stats(self) -> dict[str, int]:
        """Snapshot of internal counters: total/lite/full/cache_hit/captcha/error/retry."""
        return dict(self._stats)

    def reset_stats(self) -> None:
        for k in self._stats:
            self._stats[k] = 0

    def enable_logging(self, path: str | None = None, *, stream=None) -> None:
        """Emit one JSON line per get() to `path` (file) or `stream` (e.g. sys.stderr)."""
        from .logging import JsonLineLogger
        self._logger = JsonLineLogger(path=path, stream=stream)

    def disable_logging(self) -> None:
        self._logger = None

    def _log(self, event: str, **fields) -> None:
        if self._logger is not None:
            self._logger.emit(event, **fields)

    def _dump_debug(self, url: str, err: BaseException) -> None:
        """Write a screenshot, the last context's cookies, and an error log to debug_dir."""
        if not self.debug_dir:
            return
        import os, time
        try:
            os.makedirs(self.debug_dir, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            base = os.path.join(self.debug_dir, f"err-{stamp}")
            with open(base + ".log", "w", encoding="utf-8") as f:
                f.write(f"url: {url}\nerror: {type(err).__name__}: {err}\n")
            ctx = self._last_ctx
            if ctx is not None:
                pages = ctx.pages
                if pages:
                    try:
                        pages[-1].screenshot(path=base + ".png", full_page=True)
                    except Exception:
                        pass
                    try:
                        with open(base + ".html", "w", encoding="utf-8") as f:
                            f.write(pages[-1].content())
                    except Exception:
                        pass
        except Exception:
            pass

    # -- discovery / shortcuts -----------------------------------------------

    def sitemap(self, domain: str, *, max_urls: int = 10000) -> list[str]:
        """Discover URLs via robots.txt + sitemaps."""
        from .sitemap import discover
        return discover(self, domain, max_urls=max_urls)

    @property
    def cookies(self):
        """CookieEditor: ghost.cookies.set(name, value, domain=...)"""
        from .cookies import CookieEditor
        if not hasattr(self, "_cookie_editor"):
            self._cookie_editor = CookieEditor(self)
        return self._cookie_editor

    def download(self, url: str, path: str, *, parallel: int = 1, **kwargs):
        """Stream `url` to `path` with browser-grade TLS and resume support.

        parallel > 1 enables multi-range parallel download (falls back if server
        doesn't support Range).
        """
        if parallel and parallel > 1:
            from .downloads import download_parallel
            return download_parallel(url, path, chunks=parallel, proxy=self.proxy, **kwargs)
        from .downloads import download as _dl
        return _dl(url, path, proxy=self.proxy, **kwargs)

    def graphql(self, url: str, query_str: str, variables: dict | None = None, **kwargs):
        """Send a GraphQL query/mutation. Returns parsed JSON."""
        from .graphql import query as _gq
        return _gq(self, url, query_str, variables, **kwargs)

    def ws(self, url: str, **kwargs):
        """Open a WebSocket with browser-grade TLS. Returns a WebSocketSession."""
        from .websocket import connect, WebSocketSession
        return WebSocketSession(connect(url, proxy=self.proxy, **kwargs))
