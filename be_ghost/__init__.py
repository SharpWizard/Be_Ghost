"""Be_Ghost — ultra-lightweight stealth browser."""

from .async_browser import AsyncBeGhost
from .browser import BeGhost, CaptchaError, Response
from .cache import DiskCache
from .captcha import CaptchaInfo, detect as detect_captcha
from .diff import HtmlDiff, diff as html_diff
from .fingerprint import PROFILES, get_profile, random_profile
from .humanize import AsyncHumanPage, HumanPage
from .metadata import PageMetadata
from .pool import ContextPool
from .proxies import ProxyPool
from .ratelimit import RateLimiter
from .retry import retry_async, retry_sync

# Lite engine (no Chromium). Imports succeed only when curl_cffi + selectolax are installed.
# Use `from be_ghost.lite import LiteBrowser` directly if you need reliable imports.
try:
    from .lite.browser import AsyncLiteBrowser, LiteBrowser  # noqa: F401
except ImportError:
    pass

__version__ = "0.4.0"
__all__ = [
    "BeGhost",
    "AsyncBeGhost",
    "Response",
    "CaptchaError",
    "CaptchaInfo",
    "detect_captcha",
    "HumanPage",
    "AsyncHumanPage",
    "ProxyPool",
    "PROFILES",
    "random_profile",
    "get_profile",
    "retry_sync",
    "retry_async",
    "DiskCache",
    "RateLimiter",
    "ContextPool",
    "PageMetadata",
    "HtmlDiff",
    "html_diff",
]
