"""Detect common challenge / captcha pages from response HTML and headers."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class CaptchaInfo:
    detected: bool
    kind: str | None  # cloudflare, cloudflare_turnstile, hcaptcha, recaptcha, datadome, perimeterx, akamai
    evidence: str | None

    def __bool__(self) -> bool:
        return self.detected


# Order matters — most-specific first.
_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("cloudflare_turnstile", re.compile(r"challenges\.cloudflare\.com/turnstile|cf-turnstile", re.I)),
    ("cloudflare",            re.compile(r"<title>\s*just a moment|cf-browser-verification|__cf_chl_|cf-challenge-running|cdn-cgi/challenge-platform", re.I)),
    ("hcaptcha",              re.compile(r"hcaptcha\.com|h-captcha|js\.hcaptcha\.com", re.I)),
    ("recaptcha",             re.compile(r"google\.com/recaptcha|grecaptcha|g-recaptcha", re.I)),
    ("datadome",              re.compile(r"datadome|geo\.captcha-delivery\.com|dd-captcha", re.I)),
    ("perimeterx",            re.compile(r"_pxhd|px-captcha|captcha\.px-cdn\.net|perimeterx", re.I)),
    ("akamai",                re.compile(r"_abck|ak_bmsc|akamai.*bot", re.I)),
]


def detect(html: str, headers: dict[str, str] | None = None, status: int | None = None) -> CaptchaInfo:
    """Best-effort detection of a challenge page."""
    h = (headers or {})
    server = (h.get("server") or h.get("Server") or "").lower()

    if status in (403, 429, 503):
        if "cloudflare" in server:
            return CaptchaInfo(True, "cloudflare", f"status {status} from Cloudflare")
        if "akamai" in server:
            return CaptchaInfo(True, "akamai", f"status {status} from Akamai")

    sample = html[:200_000]  # cap regex work
    for kind, pat in _RULES:
        m = pat.search(sample)
        if m:
            return CaptchaInfo(True, kind, m.group(0))

    # Last-resort: an exact CF interstitial title. cf_clearance cookies alone
    # aren't evidence — they exist on plain CF-fronted pages too.
    if re.search(r"<title>\s*Just a moment\.\.\.\s*</title>", html, re.I):
        return CaptchaInfo(True, "cloudflare", "challenge interstitial title")

    return CaptchaInfo(False, None, None)
