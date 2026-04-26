"""Smart waiters that go beyond Playwright's built-ins.

- wait_for_text: wait until visible text appears anywhere
- wait_for_predicate: wait for a custom JS condition
- wait_for_selector_count: wait until N matching elements exist
- wait_for_quiet_network: like networkidle but ignores known telemetry hosts
"""

from __future__ import annotations

import re
import time

# Hosts to ignore when waiting for network quiet — analytics/ads/CDN keepalives
# that never settle on most sites.
IGNORED_HOSTS = re.compile(
    r"google-analytics|googletagmanager|doubleclick|facebook\.com/tr|"
    r"hotjar|sentry\.io|segment\.com|amplitude|mixpanel|datadoghq|"
    r"cloudflareinsights|newrelic\.com|fullstory|optimizely",
    re.I,
)


def wait_for_text(page, text: str, *, timeout_ms: int = 30000, case_insensitive: bool = True) -> None:
    """Block until `text` appears in the rendered DOM."""
    target = page.page if hasattr(page, "page") else page
    flags = "i" if case_insensitive else ""
    js_text = repr(text)  # safe quoted for JS
    target.wait_for_function(
        f"() => new RegExp({js_text}, {js_text and chr(34) + flags + chr(34)}).test(document.body.innerText)",
        timeout=timeout_ms,
    )


def wait_for_predicate(page, expr: str, *, timeout_ms: int = 30000) -> None:
    """Block until JS expression `expr` evaluates truthy.

    Example: ghost.wait_for_predicate(page, "document.querySelectorAll('article').length >= 10")
    """
    target = page.page if hasattr(page, "page") else page
    target.wait_for_function(f"() => Boolean({expr})", timeout=timeout_ms)


def wait_for_selector_count(page, selector: str, count: int, *, timeout_ms: int = 30000) -> None:
    """Block until at least `count` elements match `selector`."""
    target = page.page if hasattr(page, "page") else page
    target.wait_for_function(
        f"() => document.querySelectorAll({selector!r}).length >= {count}",
        timeout=timeout_ms,
    )


def wait_for_quiet_network(page, *, idle_ms: int = 500, timeout_ms: int = 30000,
                           ignore_hosts: re.Pattern[str] = IGNORED_HOSTS) -> None:
    """Wait for `idle_ms` of network silence, ignoring telemetry/ad hosts.

    More forgiving than Playwright's `networkidle` on sites that ping analytics
    every few seconds.
    """
    target = page.page if hasattr(page, "page") else page

    in_flight = {"n": 0}
    last_activity = {"t": time.monotonic()}

    def _bump():
        last_activity["t"] = time.monotonic()

    def _on_request(req):
        if not ignore_hosts.search(req.url):
            in_flight["n"] += 1
            _bump()

    def _on_finished(resp):
        try:
            url = resp.url if hasattr(resp, "url") else resp.request.url
        except Exception:
            url = ""
        if not ignore_hosts.search(url):
            in_flight["n"] = max(0, in_flight["n"] - 1)
            _bump()

    target.on("request", _on_request)
    target.on("requestfinished", _on_finished)
    target.on("requestfailed", _on_finished)

    deadline = time.monotonic() + timeout_ms / 1000.0
    threshold = idle_ms / 1000.0
    try:
        while time.monotonic() < deadline:
            quiet_for = time.monotonic() - last_activity["t"]
            if in_flight["n"] == 0 and quiet_for >= threshold:
                return
            target.wait_for_timeout(50)
        # Timed out — return without raising; caller can decide.
    finally:
        try:
            target.remove_listener("request", _on_request)
            target.remove_listener("requestfinished", _on_finished)
            target.remove_listener("requestfailed", _on_finished)
        except Exception:
            pass
