"""v0.4 additions: consent auto-accept, waiters, extraction, diff, CDP, parallel download."""

from be_ghost import BeGhost


def consent_auto_accept():
    """Cookie banners click themselves out of the way."""
    with BeGhost(mode="full", lite=False, auto_accept_consent=True) as ghost:
        with ghost.session("https://example.com", human=True) as page:
            print("title:", page.page.title())


def smart_waiters():
    """Wait for actual content, not just network silence."""
    from be_ghost.waiters import wait_for_text, wait_for_quiet_network
    with BeGhost(lite=False) as ghost:
        with ghost.session("https://news.ycombinator.com") as page:
            wait_for_text(page, "Hacker News")
            wait_for_quiet_network(page, idle_ms=300, timeout_ms=5000)


def extraction_template():
    """Declarative scraping in one call."""
    with BeGhost() as ghost:
        r = ghost.get("https://news.ycombinator.com")
        data = r.extract({
            "site_title": "title",
            "first_link": ("a.titlelink, .titleline > a", "href"),
            "story_titles": (".titleline > a", "text", "all"),
            "score_count": (".score", "int", "all"),
            "url": "@request",
        })
        print(data)


def diff_responses():
    """Detect what changed between two fetches."""
    with BeGhost() as ghost:
        r1 = ghost.get("https://example.com")
        r2 = ghost.get("https://example.com")
        d = r1.diff(r2)
        print(d)  # <HtmlDiff +0 -0, 0 text chars> means identical


def auto_debug_on_error():
    """Save screenshot + HTML when get() fails."""
    with BeGhost(lite=False, debug_dir="./debug") as ghost:
        try:
            ghost.get("https://this-domain-does-not-exist-12345.com")
        except Exception as e:
            print(f"failed (expected) — check ./debug/ for the dump: {e}")


def cdp_geolocation():
    """Override geolocation via CDP — sites that geo-fence think you're in NYC."""
    from be_ghost.cdp import set_geolocation
    with BeGhost(lite=False) as ghost:
        with ghost.session() as page:
            set_geolocation(page, lat=40.7128, lon=-74.0060)
            page.goto("https://example.com")


def parallel_download():
    """Multi-range parallel download for big files."""
    with BeGhost() as ghost:
        def cb(done, total):
            pct = done / total * 100 if total else 0
            print(f"\r {pct:.1f}%", end="", flush=True)
        ghost.download(
            "https://speed.hetzner.de/100MB.bin", "100MB.bin",
            parallel=8, on_progress=cb,
        )
        print()


if __name__ == "__main__":
    extraction_template()
    diff_responses()
