"""Production patterns: cache + rate limit + sitemap + metadata + downloads + GraphQL."""

from be_ghost import BeGhost, DiskCache, RateLimiter


def cached_polite_crawl():
    cache = DiskCache(directory=".be_ghost_cache", ttl=3600)
    rl = RateLimiter(default_rps=2.0, per_domain={"news.ycombinator.com": 4.0})
    with BeGhost(cache=cache, rate_limit=rl) as ghost:
        ghost.enable_logging(stream=__import__("sys").stderr)
        for u in ["https://news.ycombinator.com/", "https://news.ycombinator.com/news?p=2"]:
            r = ghost.get(u)
            md = r.metadata()
            print(md.title, "—", len(r.html), "bytes")
        print("stats:", ghost.stats())


def sitemap_then_extract():
    with BeGhost(mode="lite") as ghost:
        urls = ghost.sitemap("https://example.com", max_urls=200)
        print(f"found {len(urls)} urls")
        for u in urls[:5]:
            r = ghost.get(u)
            md = r.metadata()
            print(f"  {md.title or '<no title>'} :: {u}")


def download_with_progress():
    with BeGhost() as ghost:
        def cb(done, total):
            pct = (done / total * 100) if total else 0
            print(f"\r  {done:,} / {total or '?':,} bytes ({pct:.1f}%)", end="", flush=True)
        res = ghost.download("https://speed.hetzner.de/100MB.bin", "100MB.bin", on_progress=cb)
        print(f"\ndone: {res.size} bytes in {res.elapsed_ms} ms (resumed={res.resumed})")


def graphql_request():
    with BeGhost() as ghost:
        data = ghost.graphql(
            "https://countries.trevorblades.com/",
            "query { countries { code name capital } }",
        )
        for c in data["data"]["countries"][:5]:
            print(c["code"], c["name"], "—", c["capital"])


def cookies_demo():
    with BeGhost() as ghost:
        ghost.cookies.set("session", "abc123", domain=".example.com", path="/")
        print(ghost.cookies.list())
        ghost.cookies.delete("session", domain=".example.com")


if __name__ == "__main__":
    cached_polite_crawl()
    graphql_request()
