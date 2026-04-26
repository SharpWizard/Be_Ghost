"""Unit tests for pure logic — no network, no browser."""

from __future__ import annotations

import time

import pytest

from be_ghost.captcha import detect
from be_ghost.metadata import extract
from be_ghost.ratelimit import RateLimiter, _Bucket
from be_ghost.retry import retry_sync


# ---------- captcha.detect ---------------------------------------------------

class TestCaptcha:
    def test_clean_html_not_detected(self):
        assert not detect("<html><body>Hello world</body></html>")

    def test_cloudflare_just_a_moment(self):
        c = detect("<html><title>Just a moment...</title></html>")
        assert c.detected
        assert c.kind == "cloudflare"

    def test_cloudflare_turnstile(self):
        c = detect('<div class="cf-turnstile"></div>')
        assert c.detected and c.kind == "cloudflare_turnstile"

    def test_hcaptcha(self):
        c = detect('<script src="https://js.hcaptcha.com/captcha.js"></script>')
        assert c.detected and c.kind == "hcaptcha"

    def test_recaptcha(self):
        c = detect('<script src="https://www.google.com/recaptcha/api.js"></script>')
        assert c.detected and c.kind == "recaptcha"

    def test_datadome(self):
        c = detect('<iframe src="https://geo.captcha-delivery.com/x"></iframe>')
        assert c.detected and c.kind == "datadome"

    def test_status_403_with_cloudflare_server(self):
        c = detect("forbidden", headers={"server": "cloudflare"}, status=403)
        assert c.detected and c.kind == "cloudflare"

    def test_bool_protocol(self):
        c = detect("clean")
        assert not bool(c)

    def test_specificity_order_turnstile_before_cf(self):
        # Both signals present — turnstile should win because it's more specific.
        c = detect(
            '<title>Just a moment...</title>'
            '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>'
        )
        assert c.kind == "cloudflare_turnstile"


# ---------- metadata.extract -------------------------------------------------

class TestMetadata:
    def test_basic_title(self):
        md = extract("<html><head><title>Hello</title></head></html>")
        assert md.title == "Hello"

    def test_description(self):
        html = '<meta name="description" content="A test page">'
        assert extract(html).description == "A test page"

    def test_og_tags(self):
        html = (
            '<meta property="og:title" content="OG Title">'
            '<meta property="og:image" content="https://example.com/i.png">'
        )
        md = extract(html)
        assert md.og["title"] == "OG Title"
        assert md.og["image"] == "https://example.com/i.png"
        assert "https://example.com/i.png" in md.images

    def test_twitter_card(self):
        html = '<meta name="twitter:card" content="summary"><meta name="twitter:site" content="@x">'
        md = extract(html)
        assert md.twitter == {"card": "summary", "site": "@x"}

    def test_canonical(self):
        md = extract('<link rel="canonical" href="https://example.com/canonical">')
        assert md.canonical == "https://example.com/canonical"

    def test_jsonld(self):
        html = (
            '<script type="application/ld+json">{"@type":"Article","headline":"Hi"}</script>'
        )
        md = extract(html)
        assert md.jsonld == [{"@type": "Article", "headline": "Hi"}]

    def test_jsonld_invalid_skipped(self):
        html = '<script type="application/ld+json">not json</script>'
        assert extract(html).jsonld == []

    def test_description_fallback_to_og(self):
        html = '<meta property="og:description" content="From OG">'
        assert extract(html).description == "From OG"

    def test_single_quoted_attrs(self):
        html = "<meta name='description' content='single quotes'>"
        assert extract(html).description == "single quotes"


# ---------- ratelimit --------------------------------------------------------

class TestRateLimit:
    def test_bucket_first_take_is_zero_wait(self):
        b = _Bucket(rate=10.0, burst=1.0)
        assert b.take() == 0.0  # full burst available

    def test_bucket_exhausted_returns_wait(self):
        b = _Bucket(rate=2.0, burst=1.0)
        b.take()  # consume the only token
        wait = b.take()
        # 1 / 2.0 = 0.5s, but elapsed time during the call shaves a bit off
        assert 0.4 < wait <= 0.5

    def test_per_domain_isolation(self):
        rl = RateLimiter(per_domain={"a.com": 1.0, "b.com": 1.0})
        # First request on each host should not block.
        t0 = time.monotonic()
        rl.acquire("https://a.com/x")
        rl.acquire("https://b.com/x")
        assert time.monotonic() - t0 < 0.05

    def test_no_limit_means_no_wait(self):
        rl = RateLimiter()  # no defaults
        t0 = time.monotonic()
        for _ in range(100):
            rl.acquire("https://anywhere.com")
        assert time.monotonic() - t0 < 0.05


# ---------- retry ------------------------------------------------------------

class TestRetry:
    def test_success_first_try(self):
        calls = [0]
        def fn():
            calls[0] += 1
            return "ok"
        assert retry_sync(fn, attempts=3) == "ok"
        assert calls[0] == 1

    def test_success_after_retries(self):
        calls = [0]
        def fn():
            calls[0] += 1
            if calls[0] < 3:
                raise RuntimeError("nope")
            return "finally"
        assert retry_sync(fn, attempts=5, base_delay=0.01) == "finally"
        assert calls[0] == 3

    def test_exhausts_and_raises(self):
        def fn():
            raise ValueError("always fails")
        with pytest.raises(ValueError):
            retry_sync(fn, attempts=2, base_delay=0.01)


# ---------- needs_full_fallback ---------------------------------------------

class TestFallbackHeuristic:
    def _r(self, **kw):
        from be_ghost.browser import Response
        defaults = dict(
            url="https://x", status=200, headers={}, html="<html></html>",
            cookies=[], final_url="https://x", elapsed_ms=0,
        )
        defaults.update(kw)
        return Response(**defaults)

    def test_404_escalates(self):
        from be_ghost.lite.browser import needs_full_fallback
        ok, _ = needs_full_fallback(self._r(status=404))
        assert ok

    def test_captcha_escalates(self):
        from be_ghost.lite.browser import needs_full_fallback
        ok, _ = needs_full_fallback(self._r(html="<title>Just a moment...</title>"))
        assert ok

    def test_real_html_does_not_escalate(self):
        from be_ghost.lite.browser import needs_full_fallback
        body = "<html><body>" + ("<p>real content here. " * 50) + "</body></html>"
        ok, reason = needs_full_fallback(self._r(html=body))
        assert not ok, f"escalated for: {reason}"

    def test_json_body_does_not_escalate(self):
        from be_ghost.lite.browser import needs_full_fallback
        ok, _ = needs_full_fallback(self._r(
            html='{"data": [1, 2, 3]}',
            headers={"content-type": "application/json"},
        ))
        assert not ok

    def test_noscript_shell_escalates(self):
        from be_ghost.lite.browser import needs_full_fallback
        body = '<html><body><noscript>please enable javascript</noscript><div id="root"></div></body></html>'
        ok, _ = needs_full_fallback(self._r(html=body))
        assert ok

    def test_sparse_spa_shell_escalates(self):
        from be_ghost.lite.browser import needs_full_fallback
        body = '<html><body><div id="app"></div><script src="/bundle.js"></script></body></html>'
        ok, reason = needs_full_fallback(self._r(html=body))
        assert ok and "sparse" in reason

    def test_small_real_page_does_not_escalate(self):
        from be_ghost.lite.browser import needs_full_fallback
        # example.com-style: tiny but real content, no SPA mount.
        body = "<html><body><h1>Example</h1><p>Real but short content.</p></body></html>"
        ok, reason = needs_full_fallback(self._r(html=body))
        assert not ok, f"escalated on small real page: {reason}"


# ---------- sitemap parser --------------------------------------------------

class TestSitemap:
    def test_simple_url_extraction(self):
        from be_ghost.sitemap import _parse_sitemap_xml
        xml = """
        <urlset>
            <url><loc>https://example.com/a</loc></url>
            <url><loc>https://example.com/b</loc></url>
        </urlset>
        """
        pages, nested = _parse_sitemap_xml(xml, "https://example.com/sitemap.xml")
        assert "https://example.com/a" in pages
        assert "https://example.com/b" in pages
        assert nested == []

    def test_sitemap_index(self):
        from be_ghost.sitemap import _parse_sitemap_xml
        xml = """
        <sitemapindex>
            <sitemap><loc>https://example.com/sm-1.xml</loc></sitemap>
            <sitemap><loc>https://example.com/sm-2.xml</loc></sitemap>
        </sitemapindex>
        """
        pages, nested = _parse_sitemap_xml(xml, "https://example.com/sitemap.xml")
        assert "https://example.com/sm-1.xml" in nested
        assert "https://example.com/sm-2.xml" in nested


# ---------- proxy pool ------------------------------------------------------

class TestProxyPool:
    def test_round_robin(self):
        from be_ghost.proxies import ProxyPool
        p = ProxyPool(["http://a", "http://b", "http://c"])
        seen = [p.next() for _ in range(6)]
        assert seen == ["http://a", "http://b", "http://c"] * 2

    def test_random_strategy(self):
        from be_ghost.proxies import ProxyPool
        p = ProxyPool(["http://a", "http://b"], strategy="random")
        seen = {p.next() for _ in range(50)}
        assert seen == {"http://a", "http://b"}

    def test_dead_proxy_skipped(self):
        from be_ghost.proxies import ProxyPool
        p = ProxyPool(["http://a", "http://b"], max_failures=1, cooldown_seconds=60)
        for _ in range(2):
            p.mark_failure("http://a")
        # http://a is now dead — only b should be returned.
        seen = {p.next() for _ in range(10)}
        assert seen == {"http://b"}

    def test_all_dead_raises(self):
        from be_ghost.proxies import ProxyPool
        p = ProxyPool(["http://a"], max_failures=1, cooldown_seconds=60)
        p.mark_failure("http://a")
        with pytest.raises(RuntimeError):
            p.next()
