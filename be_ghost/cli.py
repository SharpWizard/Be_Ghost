"""Be_Ghost CLI — curl-style stealth fetcher + batch + self-test."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from . import config as cfg_loader
from .async_browser import AsyncBeGhost
from .browser import BeGhost
from .detect import run as run_detect, report as detect_report
from .fingerprint import PROFILES


def _parse_headers(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _common_browser_args(args, *, async_cls: bool = False):
    """Build kwargs for BeGhost / AsyncBeGhost from parsed args + config defaults."""
    defaults = cfg_loader.load()
    profile = None if args.profile == "random" else args.profile
    out = dict(defaults)
    out.update({
        "stealth": not args.no_stealth,
        "lite": not args.no_lite,
        "headless": not args.show,
        "profile": profile or out.get("profile"),
        "proxy": args.proxy or out.get("proxy"),
        "timeout_ms": args.timeout,
        "storage_state": args.storage or out.get("storage_state"),
        "trace": args.trace or out.get("trace"),
        "har_record": args.har_record or out.get("har_record"),
        "har_replay": args.har_replay or out.get("har_replay"),
        "max_bytes": args.max_bytes or out.get("max_bytes"),
        "mode": getattr(args, "mode", "auto"),
    })
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="be_ghost",
        description="Ultra-lightweight stealth browser. Fetch, batch, self-test, or run as MCP.",
    )
    sub = p.add_subparsers(dest="cmd")

    # default: fetch a single URL (back-compat: `be_ghost <url>` works)
    p.add_argument("url", nargs="?", help="URL to fetch (default subcommand)")
    p.add_argument("--output", "-o",
                   choices=["html", "text", "json", "headers", "cookies", "info", "links"],
                   default="html")
    p.add_argument("--profile", choices=[pp["name"] for pp in PROFILES] + ["random"], default="random")
    p.add_argument("--no-lite", action="store_true")
    p.add_argument("--no-stealth", action="store_true")
    p.add_argument("--show", action="store_true")
    p.add_argument("--proxy")
    p.add_argument("--headers", help="path to file with extra request headers")
    p.add_argument("--wait-until", default="domcontentloaded",
                   choices=["load", "domcontentloaded", "networkidle", "commit"])
    p.add_argument("--wait-for", help="CSS selector to wait for")
    p.add_argument("--timeout", type=int, default=30000)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument("--retry-on-captcha", action="store_true")
    p.add_argument("--storage", help="storage_state JSON path")
    p.add_argument("--screenshot", help="save full-page screenshot to PNG")
    p.add_argument("--pdf", help="save page as PDF")
    p.add_argument("--mhtml", help="save page as MHTML archive")
    p.add_argument("--trace", help="save Playwright trace to .zip")
    p.add_argument("--har-record", help="record all traffic to HAR")
    p.add_argument("--har-replay", help="replay traffic from HAR (no network)")
    p.add_argument("--max-bytes", type=int, help="abort if response total exceeds N bytes")
    p.add_argument("--auto-http", action="store_true",
                   help="try JA3-spoofed HTTP first, fall back to browser")
    p.add_argument("--mode", choices=["auto", "lite", "full"], default="auto",
                   help="auto = try lite first, fall back to Chromium; lite = no Chromium; full = always Chromium")
    p.add_argument("--list-profiles", action="store_true")
    p.add_argument("--detect", action="store_true",
                   help="run the bot-detection self-test suite and exit")

    # sitemap subcommand
    ps = sub.add_parser("sitemap", help="discover URLs via robots.txt + sitemaps")
    ps.add_argument("domain")
    ps.add_argument("--max", type=int, default=10000)

    # batch subcommand
    pb = sub.add_parser("batch", help="fetch many URLs concurrently")
    pb.add_argument("file", help="path to URL list (one per line) or - for stdin")
    pb.add_argument("--concurrency", type=int, default=5)
    pb.add_argument("--profile", choices=[pp["name"] for pp in PROFILES] + ["random"], default="random")
    pb.add_argument("--no-lite", action="store_true")
    pb.add_argument("--no-stealth", action="store_true")
    pb.add_argument("--show", action="store_true")
    pb.add_argument("--proxy")
    pb.add_argument("--timeout", type=int, default=30000)
    pb.add_argument("--storage")
    pb.add_argument("--auto-http", action="store_true")
    pb.add_argument("--out-dir", help="write each response HTML to a file in this dir")
    pb.add_argument("--retries", type=int, default=0)
    return p


def _emit(args, ghost, r):
    out = args.output
    if out == "html":
        sys.stdout.write(r.html)
    elif out == "text":
        try:
            sys.stdout.write(r.text_only())
        except ImportError:
            print("error: --output text requires selectolax (pip install 'be_ghost[parse]')", file=sys.stderr)
            return 2
    elif out == "json":
        try:
            json.dump(r.json(), sys.stdout, indent=2)
        except json.JSONDecodeError:
            print("error: response body is not valid JSON", file=sys.stderr)
            return 2
    elif out == "headers":
        for k, v in r.headers.items():
            print(f"{k}: {v}")
    elif out == "cookies":
        json.dump(r.cookies, sys.stdout, indent=2)
    elif out == "links":
        try:
            for href in r.links():
                print(href)
        except ImportError:
            print("error: --output links requires selectolax", file=sys.stderr)
            return 2
    elif out == "info":
        cap = r.captcha
        print(f"profile:    {ghost.profile.get('name')}")
        print(f"status:     {r.status}")
        print(f"final_url:  {r.final_url}")
        print(f"elapsed:    {r.elapsed_ms} ms")
        print(f"body_size:  {len(r.html)} bytes")
        print(f"cookies:    {len(r.cookies)}")
        print(f"captcha:    {cap.kind if cap.detected else 'no'}")
    return 0


def _cmd_batch(args) -> int:
    if args.file == "-":
        urls = [u.strip() for u in sys.stdin if u.strip()]
    else:
        urls = [u.strip() for u in Path(args.file).read_text(encoding="utf-8").splitlines() if u.strip()]
    if not urls:
        print("no URLs", file=sys.stderr)
        return 1

    profile = None if args.profile == "random" else args.profile
    out_dir = Path(args.out_dir) if args.out_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    async def run():
        async with AsyncBeGhost(
            stealth=not args.no_stealth,
            lite=not args.no_lite,
            headless=not args.show,
            profile=profile,
            proxy=args.proxy,
            timeout_ms=args.timeout,
            storage_state=args.storage,
        ) as ghost:
            results = await ghost.get_many(
                urls, concurrency=args.concurrency,
                auto_http=args.auto_http, retries=args.retries,
            )
            for url, r in zip(urls, results, strict=False):
                if isinstance(r, BaseException):
                    print(f"FAIL  {url}  ({type(r).__name__}: {r})", file=sys.stderr)
                    continue
                tag = "OK" if r.ok else f"{r.status}"
                cap = " [captcha]" if r.captcha else ""
                print(f"{tag:>4}  {r.elapsed_ms:>5}ms  {len(r.html):>7}b{cap}  {r.final_url}")
                if out_dir:
                    safe = "".join(c if c.isalnum() else "_" for c in url)[:120]
                    (out_dir / f"{safe}.html").write_text(r.html, encoding="utf-8")
        return 0

    return asyncio.run(run())


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "batch":
        return _cmd_batch(args)

    if args.cmd == "sitemap":
        with BeGhost(mode="lite") as g:
            urls = g.sitemap(args.domain, max_urls=args.max)
        for u in urls:
            print(u)
        return 0

    if args.list_profiles:
        for pp in PROFILES:
            print(f"{pp['name']:<20} {pp['user_agent']}")
        return 0

    if args.detect:
        with BeGhost(stealth=not args.no_stealth, lite=False, headless=not args.show,
                     profile=None if args.profile == "random" else args.profile) as g:
            results = run_detect(g)
        print(detect_report(results))
        overall = sum(r.score for r in results) / max(1, len(results))
        return 0 if overall >= 0.7 else 1

    if not args.url:
        parser.print_help()
        return 0

    headers = _parse_headers(args.headers) if args.headers else None
    kwargs = _common_browser_args(args)
    ghost = BeGhost(**kwargs)

    with ghost:
        try:
            r = ghost.get(
                args.url,
                wait_until=args.wait_until,
                wait_for=args.wait_for,
                headers=headers,
                retries=args.retries,
                retry_on_captcha=args.retry_on_captcha,
                screenshot=args.screenshot,
                pdf=args.pdf,
                mhtml=args.mhtml,
                auto_http=args.auto_http,
            )
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        return _emit(args, ghost, r) or 0


if __name__ == "__main__":
    sys.exit(main())
