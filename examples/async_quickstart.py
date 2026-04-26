"""Async Be_Ghost — concurrent fetches and interactive sessions."""

import asyncio

from be_ghost import AsyncBeGhost


async def http_like():
    async with AsyncBeGhost(stealth=True, lite=True) as ghost:
        urls = [
            "https://httpbin.org/headers",
            "https://httpbin.org/user-agent",
            "https://httpbin.org/ip",
        ]
        # Concurrent fetches share one browser; each gets its own context.
        results = await asyncio.gather(*(ghost.get(u) for u in urls))
        for r in results:
            print(r)


async def interactive():
    async with AsyncBeGhost(stealth=True, lite=False) as ghost:
        async with ghost.session("https://example.com") as page:
            print("title:", await page.title())
            print("h1:", await page.locator("h1").inner_text())


async def main():
    await http_like()
    await interactive()


if __name__ == "__main__":
    asyncio.run(main())
