"""Hybrid mode: lite engine (no Chromium) with auto-fallback to full.

Install: pip install -e ".[lite]"   (or [full] for everything)
"""

import asyncio
from be_ghost import AsyncBeGhost, BeGhost, LiteBrowser


# 1. Pure lite — no Chromium ever runs. Fastest, lowest RAM.
def lite_only():
    with BeGhost(mode="lite") as ghost:
        r = ghost.get("https://news.ycombinator.com")
        print("status:", r.status, "size:", len(r.html))
        print("titles:")
        for t in r.select_text(".titleline > a")[:5]:
            print(" ·", t)


# 2. LiteBrowser direct — same shape, no router overhead.
def lite_direct():
    with LiteBrowser() as ghost:
        with ghost.session("https://example.com") as page:
            print(page.title())
            print(page.text_content("h1"))
            page.goto("/about")  # follows the link in the same session
            print(page.url)


# 3. Auto mode (default) — tries lite, falls back to Chromium when needed.
def auto():
    with BeGhost(mode="auto") as ghost:
        # Static HTML — handled by lite (no Chromium spawned).
        r1 = ghost.get("https://example.com")
        print("ex.com:", r1.status, len(r1.html), "bytes")

        # SPA / JS-heavy — auto-detects the empty shell and escalates to Chromium.
        r2 = ghost.get("https://twitter.com")  # will fall back to full
        print("twitter:", r2.status, len(r2.html), "bytes")


# 4. Force full for one call when you know you need rendering.
def force_full_once():
    with BeGhost(mode="lite") as ghost:
        # screenshots auto-force full mode regardless of self.mode
        ghost.get("https://example.com", screenshot="ex.png")


# 5. Concurrent lite batch — single thread, hundreds of req/s.
async def batch_lite():
    urls = [f"https://httpbin.org/anything?i={i}" for i in range(50)]
    async with AsyncBeGhost(mode="lite") as ghost:
        results = await ghost.get_many(urls, concurrency=20)
        ok = sum(1 for r in results if not isinstance(r, Exception) and r.ok)
        print(f"{ok}/{len(urls)} ok")


if __name__ == "__main__":
    lite_only()
    lite_direct()
    asyncio.run(batch_lite())
