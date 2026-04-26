"""Auto-accept cookie consent banners.

Recognizes common providers (OneTrust, Cookiebot, CookieYes, Quantcast, EU GDPR
shells, Google's "Reject all"/"Accept all" prompts) and clicks the accept
button so the rest of the page becomes scrapeable.
"""

from __future__ import annotations

# (provider name, list-of-selectors). Order matters — first that matches wins.
SELECTORS: list[tuple[str, list[str]]] = [
    ("onetrust", [
        "button#onetrust-accept-btn-handler",
        "button.optanon-allow-all",
    ]),
    ("cookiebot", [
        "button#CybotCookiebotDialogBodyButtonAccept",
        "button#CybotCookiebotDialogBodyLevelButtonAcceptAll",
        "button#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    ]),
    ("cookieyes", [
        "button.cky-btn-accept",
        "button[data-cky-tag=accept-button]",
    ]),
    ("quantcast", [
        "button.qc-cmp2-accept-all",
        "button.qc-cmp-button[mode='primary']",
    ]),
    ("trustarc", [
        "a.call",
        "div#truste-consent-button",
    ]),
    ("usercentrics", [
        "button[data-testid='uc-accept-all-button']",
    ]),
    ("didomi", [
        "button#didomi-notice-agree-button",
    ]),
    ("google_fc", [
        ".fc-cta-consent",
        ".fc-button.fc-cta-consent",
    ]),
    ("eu_generic_text", [
        # Last-ditch: any visible button with "Accept all" / "Allow all" / "I agree" text.
        # Used as a fallback when no known provider matches.
        "button:has-text('Accept all')",
        "button:has-text('Allow all')",
        "button:has-text('I agree')",
        "button:has-text('Got it')",
    ]),
]


def accept(page, *, timeout_ms: int = 1500) -> str | None:
    """Try every known consent selector. Returns the provider name that matched, or None.

    Pass either a Playwright Page or a HumanPage wrapper. Non-blocking — won't
    raise if no banner is present; just returns None.
    """
    target = page.page if hasattr(page, "page") else page
    for name, selectors in SELECTORS:
        for sel in selectors:
            try:
                loc = target.locator(sel).first
                if loc.count() and loc.is_visible(timeout=timeout_ms):
                    loc.click(timeout=timeout_ms)
                    target.wait_for_timeout(200)
                    return name
            except Exception:
                continue
    return None


async def accept_async(page, *, timeout_ms: int = 1500) -> str | None:
    """Async variant for AsyncBeGhost / Playwright async Page."""
    target = page.page if hasattr(page, "page") else page
    for name, selectors in SELECTORS:
        for sel in selectors:
            try:
                loc = target.locator(sel).first
                if await loc.count() and await loc.is_visible(timeout=timeout_ms):
                    await loc.click(timeout=timeout_ms)
                    await target.wait_for_timeout(200)
                    return name
            except Exception:
                continue
    return None
