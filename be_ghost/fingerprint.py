"""Realistic fingerprint profiles. Each profile is internally consistent —
UA matches platform, Sec-CH-UA matches UA major, GL vendor matches OS,
languages match locale.
"""

from __future__ import annotations

import random


# Bump CHROME_MAJOR when you upgrade the bundled Chromium. Sec-CH-UA values are
# derived from this — keep them in sync.
CHROME_MAJOR = 132
CHROME_FULL = "132.0.6834.84"


def _chua(brands: list[tuple[str, str]]) -> str:
    return ", ".join(f'"{n}";v="{v}"' for n, v in brands)


def _chua_ff(brands: list[tuple[str, str]]) -> str:
    return ", ".join(f'"{n}";v="{v}"' for n, v in brands)


_BRANDS = [("Not A(Brand", "8"), ("Chromium", str(CHROME_MAJOR)), ("Google Chrome", str(CHROME_MAJOR))]
_BRANDS_FULL = [
    ("Not A(Brand", "8.0.0.0"),
    ("Chromium", CHROME_FULL),
    ("Google Chrome", CHROME_FULL),
]


def _client_hints(platform_ch: str, mobile: bool = False) -> dict[str, str]:
    return {
        "sec-ch-ua": _chua(_BRANDS),
        "sec-ch-ua-mobile": "?1" if mobile else "?0",
        "sec-ch-ua-platform": f'"{platform_ch}"',
        "sec-ch-ua-full-version-list": _chua_ff(_BRANDS_FULL),
        "sec-ch-ua-platform-version": '"15.0.0"' if platform_ch == "Windows" else '"14.0.0"',
        "sec-ch-ua-arch": '"x86"',
        "sec-ch-ua-bitness": '"64"',
        "sec-ch-ua-model": '""',
        "sec-ch-ua-wow64": "?0",
    }


PROFILES = [
    {
        "name": "win11_chrome",
        "user_agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      f"(KHTML, like Gecko) Chrome/{CHROME_MAJOR}.0.0.0 Safari/537.36",
        "platform": "Win32",
        "languages": ["en-US", "en"],
        "viewport": {"width": 1920, "height": 1080},
        "screen": {"width": 1920, "height": 1080},
        "device_scale_factor": 1.0,
        "timezone": "America/New_York",
        "locale": "en-US",
        "gl_vendor": "Google Inc. (Intel)",
        "gl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "cores": 8,
        "memory": 8,
        "client_hints": _client_hints("Windows"),
    },
    {
        "name": "win10_chrome",
        "user_agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      f"(KHTML, like Gecko) Chrome/{CHROME_MAJOR}.0.0.0 Safari/537.36",
        "platform": "Win32",
        "languages": ["en-US", "en"],
        "viewport": {"width": 1366, "height": 768},
        "screen": {"width": 1366, "height": 768},
        "device_scale_factor": 1.0,
        "timezone": "America/Chicago",
        "locale": "en-US",
        "gl_vendor": "Google Inc. (NVIDIA)",
        "gl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "cores": 12,
        "memory": 16,
        "client_hints": _client_hints("Windows"),
    },
    {
        "name": "mac_chrome",
        "user_agent": f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      f"(KHTML, like Gecko) Chrome/{CHROME_MAJOR}.0.0.0 Safari/537.36",
        "platform": "MacIntel",
        "languages": ["en-US", "en"],
        "viewport": {"width": 1440, "height": 900},
        "screen": {"width": 1440, "height": 900},
        "device_scale_factor": 2.0,
        "timezone": "America/Los_Angeles",
        "locale": "en-US",
        "gl_vendor": "Google Inc. (Apple)",
        "gl_renderer": "ANGLE (Apple, Apple M1, OpenGL 4.1)",
        "cores": 8,
        "memory": 8,
        "client_hints": _client_hints("macOS"),
    },
    {
        "name": "linux_chrome",
        "user_agent": f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      f"(KHTML, like Gecko) Chrome/{CHROME_MAJOR}.0.0.0 Safari/537.36",
        "platform": "Linux x86_64",
        "languages": ["en-US", "en"],
        "viewport": {"width": 1920, "height": 1080},
        "screen": {"width": 1920, "height": 1080},
        "device_scale_factor": 1.0,
        "timezone": "Europe/London",
        "locale": "en-GB",
        "gl_vendor": "Mesa",
        "gl_renderer": "Mesa Intel(R) UHD Graphics (TGL GT1)",
        "cores": 4,
        "memory": 8,
        "client_hints": _client_hints("Linux"),
    },
    {
        "name": "iphone_safari",
        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
                      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
        "platform": "iPhone",
        "languages": ["en-US", "en"],
        "viewport": {"width": 390, "height": 844},
        "screen": {"width": 390, "height": 844},
        "device_scale_factor": 3.0,
        "timezone": "America/New_York",
        "locale": "en-US",
        "gl_vendor": "Apple Inc.",
        "gl_renderer": "Apple GPU",
        "cores": 6,
        "memory": 4,
        "client_hints": {},  # Safari does not send Sec-CH-UA
    },
    {
        "name": "android_chrome",
        "user_agent": f"Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
                      f"(KHTML, like Gecko) Chrome/{CHROME_MAJOR}.0.0.0 Mobile Safari/537.36",
        "platform": "Linux armv8l",
        "languages": ["en-US", "en"],
        "viewport": {"width": 412, "height": 915},
        "screen": {"width": 412, "height": 915},
        "device_scale_factor": 2.625,
        "timezone": "America/New_York",
        "locale": "en-US",
        "gl_vendor": "Google Inc. (Qualcomm)",
        "gl_renderer": "ANGLE (Qualcomm, Adreno (TM) 740, OpenGL ES 3.2)",
        "cores": 8,
        "memory": 8,
        "client_hints": _client_hints("Android", mobile=True),
    },
]


def random_profile(seed: int | None = None) -> dict:
    rng = random.Random(seed)
    profile = dict(rng.choice(PROFILES))
    profile["canvas_seed"] = rng.random() * 0.0001
    return profile


def get_profile(name: str) -> dict:
    for p in PROFILES:
        if p["name"] == name:
            return dict(p)
    raise ValueError(f"unknown profile: {name}. available: {[p['name'] for p in PROFILES]}")


def curl_impersonate_target() -> str:
    """Closest curl_cffi impersonation target for the bundled Chrome version.

    curl_cffi ships specific Chrome versions only — pick the closest one ≤ CHROME_MAJOR.
    """
    # curl_cffi 0.14: chrome99/100/101/104/107/110/116/119/120/123/124/131
    available = [99, 100, 101, 104, 107, 110, 116, 119, 120, 123, 124, 131]
    closest = max((v for v in available if v <= CHROME_MAJOR), default=available[-1])
    return f"chrome{closest}"
