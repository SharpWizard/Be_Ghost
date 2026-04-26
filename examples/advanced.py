"""Be_Ghost advanced features:
  - persistent storage_state (stay logged in across runs)
  - captcha detection
  - retry with backoff
  - human-like input
  - concurrent batch fetch
"""

import asyncio
from be_ghost import AsyncBeGhost, BeGhost


# 1. Persistent login: cookies + localStorage saved between runs.
def persistent_session():
    with BeGhost(storage_state="state.json", lite=False) as ghost:
        with ghost.session("https://github.com/login") as page:
            # First run: log in manually or programmatically.
            # state.json is written automatically when the session closes.
            print(page.title())


# 2. Captcha detection + retry on challenge page.
def captcha_aware():
    with BeGhost() as ghost:
        r = ghost.get("https://example.com", retries=2, retry_on_captcha=True)
        if r.captcha:
            print(f"blocked: {r.captcha.kind} -- {r.captcha.evidence}")
        else:
            print(f"ok: {r.status}, {len(r.html)} bytes")


# 3. Human-like clicks and typing.
def human_input():
    with BeGhost(lite=False) as ghost:
        with ghost.session("https://duckduckgo.com", human=True) as page:
            page.type("input[name=q]", "be ghost browser", typo_rate=0.05)
            page.click("button[type=submit]")
            page.page.wait_for_selector("article")
            page.scroll(total=2000)


# 4. Concurrent fetches with concurrency cap.
async def batch():
    urls = [f"https://httpbin.org/anything?i={i}" for i in range(10)]
    async with AsyncBeGhost() as ghost:
        results = await ghost.get_many(urls, concurrency=4)
        for r in results:
            if isinstance(r, Exception):
                print("err:", r)
            else:
                print(r.status, r.elapsed_ms, "ms")


if __name__ == "__main__":
    captcha_aware()
    asyncio.run(batch())
    # human_input()         # uncomment to try (opens a real session)
    # persistent_session()  # uncomment for login flows
