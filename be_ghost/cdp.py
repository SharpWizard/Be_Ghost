"""Chrome DevTools Protocol helpers for things Playwright doesn't expose nicely.

Use only with mode='full' — these touch the Chromium CDP session, so they have
no meaning in lite mode.

    from be_ghost.cdp import set_geolocation, throttle_network, clear_service_workers

    with ghost.session() as page:
        set_geolocation(page, lat=40.7128, lon=-74.0060, accuracy=10)
        throttle_network(page, download_kbps=1500, upload_kbps=750, latency_ms=40)
        clear_service_workers(page, "https://example.com")
"""

from __future__ import annotations


def _cdp(page):
    target = page.page if hasattr(page, "page") else page
    return target.context.new_cdp_session(target)


def set_geolocation(page, *, lat: float, lon: float, accuracy: float = 100.0) -> None:
    """Override geolocation for the page's context."""
    target = page.page if hasattr(page, "page") else page
    target.context.set_geolocation({"latitude": lat, "longitude": lon, "accuracy": accuracy})
    target.context.grant_permissions(["geolocation"])


def throttle_network(page, *, download_kbps: int = 1500, upload_kbps: int = 750,
                     latency_ms: int = 40, offline: bool = False) -> None:
    """Emulate a slower network. kbps -> bytes/s conversion done internally."""
    cdp = _cdp(page)
    cdp.send("Network.emulateNetworkConditions", {
        "offline": offline,
        "downloadThroughput": int(download_kbps * 125),  # kbps → B/s (1 KB = 1000 bits / 8)
        "uploadThroughput": int(upload_kbps * 125),
        "latency": latency_ms,
    })


def clear_network_throttling(page) -> None:
    cdp = _cdp(page)
    cdp.send("Network.emulateNetworkConditions", {
        "offline": False, "downloadThroughput": -1, "uploadThroughput": -1, "latency": 0,
    })


def clear_service_workers(page, origin: str | None = None) -> None:
    """Unregister all service workers. Useful when stale SW serves cached HTML."""
    cdp = _cdp(page)
    if origin:
        cdp.send("ServiceWorker.unregister", {"scopeURL": origin})
    else:
        cdp.send("ServiceWorker.disable")
        cdp.send("ServiceWorker.enable")


def set_device_metrics(page, *, width: int, height: int, dpr: float = 1.0, mobile: bool = False) -> None:
    """Override viewport at the device level. More thorough than Playwright's set_viewport_size."""
    cdp = _cdp(page)
    cdp.send("Emulation.setDeviceMetricsOverride", {
        "width": width, "height": height, "deviceScaleFactor": dpr, "mobile": mobile,
    })


def clear_browser_cache(page) -> None:
    cdp = _cdp(page)
    cdp.send("Network.clearBrowserCache")
    cdp.send("Network.clearBrowserCookies")


def disable_cache(page, disabled: bool = True) -> None:
    """Force cache miss for every request — useful when testing with fresh state."""
    cdp = _cdp(page)
    cdp.send("Network.setCacheDisabled", {"cacheDisabled": disabled})


def set_user_agent_override(page, ua: str, *, accept_language: str | None = None,
                             platform: str | None = None) -> None:
    """Override UA + Sec-CH-UA in one CDP call (works on iframes, not just top-level)."""
    cdp = _cdp(page)
    args: dict = {"userAgent": ua}
    if accept_language:
        args["acceptLanguage"] = accept_language
    if platform:
        args["platform"] = platform
    cdp.send("Network.setUserAgentOverride", args)
