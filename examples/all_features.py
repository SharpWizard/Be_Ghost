"""Tour of every Be_Ghost capability. Comment in/out the sections you want."""

import asyncio

from be_ghost import AsyncBeGhost, BeGhost, ProxyPool


# 1. JA3-spoofed HTTP fallback (auto_http=True)
def http_fallback():
    with BeGhost() as ghost:
        # for plain APIs / static HTML, never spawns a page if curl_cffi works.
        r = ghost.get("https://httpbin.org/json", auto_http=True)
        print(r.status, r.json())


# 2. Proxy rotation pool
def with_proxy_pool():
    pool = ProxyPool([
        "http://user:pass@proxy1:8080",
        "http://user:pass@proxy2:8080",
    ])
    with BeGhost(proxy_pool=pool) as ghost:
        for _ in range(5):
            r = ghost.get("https://httpbin.org/ip")
            print(r.html[:120])


# 3. CSS extraction with selectolax
def css_extract():
    with BeGhost() as ghost:
        r = ghost.get("https://news.ycombinator.com")
        titles = r.select_text(".titleline > a")[:10]
        for t in titles:
            print("·", t)


# 4. Pagination
def paginate():
    with BeGhost() as ghost:
        for i, r in enumerate(ghost.paginate(
            "https://news.ycombinator.com",
            next_selector="a.morelink",
            max_pages=3,
        )):
            print(f"page {i+1}: {len(r.html)} bytes from {r.final_url}")


# 5. Form filler with humanized typing
def form_fill():
    with BeGhost(lite=False) as ghost:
        with ghost.session("https://duckduckgo.com", human=True) as page:
            page.fill_form({"input[name=q]": "be ghost browser"}, submit="button[type=submit]")
            page.page.wait_for_selector("article")


# 6. Capture: screenshot + PDF + MHTML in one go
def capture_all():
    with BeGhost(lite=False) as ghost:
        ghost.get(
            "https://example.com",
            screenshot="example.png",
            pdf="example.pdf",
            mhtml="example.mhtml",
        )


# 7. Trace recording for debugging
def trace_run():
    with BeGhost(trace="run.zip") as ghost:
        ghost.get("https://example.com")
    # open with: playwright show-trace run.zip


# 8. HAR record then offline replay
def har_record_replay():
    with BeGhost(har_record="cap.har", lite=False) as ghost:
        ghost.get("https://example.com")
    # later — zero network:
    with BeGhost(har_replay="cap.har", lite=False) as ghost:
        r = ghost.get("https://example.com")
        print("served from HAR:", len(r.html), "bytes")


# 9. Resource budget (kill page if it goes over 5 MB)
def budget():
    with BeGhost(max_bytes=5 * 1024 * 1024) as ghost:
        try:
            r = ghost.get("https://example.com")
            print(r.status, len(r.html))
        except Exception as e:
            print("aborted:", e)


# 10. Run the built-in detection self-test
def selftest():
    from be_ghost.detect import run, report
    with BeGhost(lite=False) as ghost:
        results = run(ghost)
    print(report(results))


# 11. Concurrent batch with auto_http fallback
async def batch_with_fallback():
    urls = [f"https://httpbin.org/anything?i={i}" for i in range(20)]
    async with AsyncBeGhost() as ghost:
        results = await ghost.get_many(urls, concurrency=5, auto_http=True)
        ok = sum(1 for r in results if not isinstance(r, Exception) and r.ok)
        print(f"{ok}/{len(urls)} ok")


if __name__ == "__main__":
    http_fallback()
    css_extract()
    asyncio.run(batch_with_fallback())
    selftest()
