"""Human-like input — mouse curves, typing cadence, scrolling.

Behavioral signals matter to advanced detectors as much as fingerprints.
These helpers add plausible noise to clicks, typing, and scrolling.
"""

from __future__ import annotations

import math
import random


def _bezier(p0, p1, p2, p3, t):
    u = 1 - t
    return (
        u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
    )


def _curve_points(start, end, steps: int = 25, jitter: float = 0.25):
    """Cubic-bezier path with two random control points biased perpendicular to the line."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    dist = max(1.0, math.hypot(dx, dy))
    perp = (-dy / dist, dx / dist)
    mag = dist * jitter

    c1 = (
        start[0] + dx * 0.33 + perp[0] * random.uniform(-mag, mag),
        start[1] + dy * 0.33 + perp[1] * random.uniform(-mag, mag),
    )
    c2 = (
        start[0] + dx * 0.66 + perp[0] * random.uniform(-mag, mag),
        start[1] + dy * 0.66 + perp[1] * random.uniform(-mag, mag),
    )
    return [_bezier(start, c1, c2, end, i / steps) for i in range(1, steps + 1)]


# ---------- sync helpers ----------

class HumanPage:
    """Wraps a Playwright Page with human-like interaction primitives."""

    def __init__(self, page) -> None:
        self.page = page
        self._mouse_x = 0.0
        self._mouse_y = 0.0

    def move_to(self, x: float, y: float, *, steps: int = 25, jitter: float = 0.25) -> None:
        for px, py in _curve_points((self._mouse_x, self._mouse_y), (x, y), steps, jitter):
            self.page.mouse.move(px, py)
            self.page.wait_for_timeout(random.randint(4, 14))
        self._mouse_x, self._mouse_y = x, y

    def click(self, selector: str, *, jitter_px: int = 4, hover_ms: tuple[int, int] = (60, 220)) -> None:
        loc = self.page.locator(selector)
        box = loc.bounding_box()
        if not box:
            loc.click()
            return
        tx = box["x"] + box["width"] / 2 + random.uniform(-jitter_px, jitter_px)
        ty = box["y"] + box["height"] / 2 + random.uniform(-jitter_px, jitter_px)
        self.move_to(tx, ty)
        self.page.wait_for_timeout(random.randint(*hover_ms))
        self.page.mouse.down()
        self.page.wait_for_timeout(random.randint(40, 110))
        self.page.mouse.up()

    def type(self, selector: str, text: str, *, wpm: tuple[int, int] = (180, 320), typo_rate: float = 0.0) -> None:
        self.click(selector)
        for ch in text:
            if typo_rate and random.random() < typo_rate:
                wrong = chr(random.randint(97, 122))
                self.page.keyboard.type(wrong)
                self.page.wait_for_timeout(random.randint(80, 200))
                self.page.keyboard.press("Backspace")
                self.page.wait_for_timeout(random.randint(60, 140))
            self.page.keyboard.type(ch)
            self.page.wait_for_timeout(random.randint(*wpm) // 5)

    def scroll(self, *, total: int = 1500, step: tuple[int, int] = (80, 180), pause_ms: tuple[int, int] = (80, 260)) -> None:
        scrolled = 0
        while scrolled < total:
            d = random.randint(*step)
            self.page.mouse.wheel(0, d)
            scrolled += d
            self.page.wait_for_timeout(random.randint(*pause_ms))

    def fill_form(self, fields: dict[str, str], *, submit: str | None = None, typo_rate: float = 0.0) -> None:
        """Fill a form from {selector: value}. Optionally click a submit selector."""
        for selector, value in fields.items():
            self.type(selector, value, typo_rate=typo_rate)
            self.page.wait_for_timeout(random.randint(120, 380))
        if submit:
            self.click(submit)

    def submit_form_with_csrf(self, form_selector: str, fields: dict[str, str], *,
                              submit: str | None = None, csrf_names: tuple[str, ...] = ("_csrf", "csrf_token", "authenticity_token", "__RequestVerificationToken")) -> None:
        """Fill a form, preserving any hidden CSRF tokens already in the DOM.

        Looks for hidden inputs matching common CSRF names within `form_selector`
        and skips them — they keep their server-issued value.
        """
        form = self.page.locator(form_selector)
        # Identify CSRF input names actually present so we don't clobber them.
        present = set()
        for name in csrf_names:
            if form.locator(f'input[name="{name}"]').count():
                present.add(name)
        safe_fields = {k: v for k, v in fields.items() if not any(n in k for n in present)}
        for selector, value in safe_fields.items():
            self.type(selector, value)
            self.page.wait_for_timeout(random.randint(120, 380))
        if submit:
            self.click(submit)


# ---------- async helpers ----------

class AsyncHumanPage:
    """Async variant of HumanPage."""

    def __init__(self, page) -> None:
        self.page = page
        self._mouse_x = 0.0
        self._mouse_y = 0.0

    async def move_to(self, x: float, y: float, *, steps: int = 25, jitter: float = 0.25) -> None:
        for px, py in _curve_points((self._mouse_x, self._mouse_y), (x, y), steps, jitter):
            await self.page.mouse.move(px, py)
            await self.page.wait_for_timeout(random.randint(4, 14))
        self._mouse_x, self._mouse_y = x, y

    async def click(self, selector: str, *, jitter_px: int = 4, hover_ms: tuple[int, int] = (60, 220)) -> None:
        loc = self.page.locator(selector)
        box = await loc.bounding_box()
        if not box:
            await loc.click()
            return
        tx = box["x"] + box["width"] / 2 + random.uniform(-jitter_px, jitter_px)
        ty = box["y"] + box["height"] / 2 + random.uniform(-jitter_px, jitter_px)
        await self.move_to(tx, ty)
        await self.page.wait_for_timeout(random.randint(*hover_ms))
        await self.page.mouse.down()
        await self.page.wait_for_timeout(random.randint(40, 110))
        await self.page.mouse.up()

    async def type(self, selector: str, text: str, *, wpm: tuple[int, int] = (180, 320), typo_rate: float = 0.0) -> None:
        await self.click(selector)
        for ch in text:
            if typo_rate and random.random() < typo_rate:
                wrong = chr(random.randint(97, 122))
                await self.page.keyboard.type(wrong)
                await self.page.wait_for_timeout(random.randint(80, 200))
                await self.page.keyboard.press("Backspace")
                await self.page.wait_for_timeout(random.randint(60, 140))
            await self.page.keyboard.type(ch)
            await self.page.wait_for_timeout(random.randint(*wpm) // 5)

    async def scroll(self, *, total: int = 1500, step: tuple[int, int] = (80, 180), pause_ms: tuple[int, int] = (80, 260)) -> None:
        scrolled = 0
        while scrolled < total:
            d = random.randint(*step)
            await self.page.mouse.wheel(0, d)
            scrolled += d
            await self.page.wait_for_timeout(random.randint(*pause_ms))

    async def fill_form(self, fields: dict[str, str], *, submit: str | None = None, typo_rate: float = 0.0) -> None:
        for selector, value in fields.items():
            await self.type(selector, value, typo_rate=typo_rate)
            await self.page.wait_for_timeout(random.randint(120, 380))
        if submit:
            await self.click(submit)
