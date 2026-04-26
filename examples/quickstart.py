"""Be_Ghost quickstart — HTTP-like and interactive session modes."""

from be_ghost import BeGhost


def http_like():
    # One-shot scrape: behaves like requests.get() but with a real browser.
    with BeGhost(stealth=True, lite=True) as ghost:
        r = ghost.get("https://httpbin.org/headers")
        print(r)
        print("status:", r.status)
        print("final url:", r.final_url)
        print("elapsed:", r.elapsed_ms, "ms")
        print("body bytes:", len(r.html))


def interactive():
    # Full automation when the task needs clicks, JS execution, etc.
    with BeGhost(stealth=True, lite=False) as ghost:
        with ghost.session("https://example.com") as page:
            print("title:", page.title())
            print("h1:", page.locator("h1").inner_text())


if __name__ == "__main__":
    http_like()
    interactive()
