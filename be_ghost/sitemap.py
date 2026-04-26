"""Sitemap discovery and crawl. Reads /robots.txt for Sitemap: directives,
falls back to /sitemap.xml, recurses into sitemap index files."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

# Lazy-import lxml for parsing — fall back to regex if unavailable.
try:
    from lxml import etree  # type: ignore[import-not-found]
    _HAS_LXML = True
except ImportError:
    _HAS_LXML = False


_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
_SITEMAP_RE = re.compile(r"<sitemap>(.*?)</sitemap>", re.S | re.I)
_SITEMAP_DIRECTIVE = re.compile(r"^\s*sitemap\s*:\s*(\S+)", re.I | re.M)


def _parse_sitemap_xml(xml: str, base: str) -> tuple[list[str], list[str]]:
    """Return (page_urls, nested_sitemap_urls)."""
    if _HAS_LXML:
        try:
            root = etree.fromstring(xml.encode("utf-8", errors="replace"))
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            pages = [el.text.strip() for el in root.findall(".//sm:url/sm:loc", ns) if el.text]
            sitemaps = [el.text.strip() for el in root.findall(".//sm:sitemap/sm:loc", ns) if el.text]
            if pages or sitemaps:
                return pages, sitemaps
        except Exception:
            pass
    # Regex fallback works fine on well-formed sitemaps.
    nested_blocks = _SITEMAP_RE.findall(xml)
    nested = []
    for block in nested_blocks:
        m = _LOC_RE.search(block)
        if m:
            nested.append(m.group(1))
    if nested:
        # Strip the <sitemap> blocks before extracting <url><loc>.
        rest = _SITEMAP_RE.sub("", xml)
        pages = _LOC_RE.findall(rest)
    else:
        pages = _LOC_RE.findall(xml)
    return pages, nested


def discover(ghost, domain: str, *, max_urls: int = 10000, max_sitemaps: int = 50) -> list[str]:
    """Discover URLs via robots.txt + sitemaps. Uses ghost.get() — respects mode."""
    if "://" not in domain:
        domain = "https://" + domain
    parsed = urlparse(domain)
    root = f"{parsed.scheme}://{parsed.netloc}"

    seeds: list[str] = []
    try:
        r = ghost.get(urljoin(root, "/robots.txt"), force="lite")
        if r.ok:
            for m in _SITEMAP_DIRECTIVE.finditer(r.html):
                seeds.append(m.group(1).strip())
    except Exception:
        pass

    if not seeds:
        seeds = [urljoin(root, "/sitemap.xml")]

    seen_sitemaps: set[str] = set()
    queue = list(seeds)
    pages: list[str] = []

    while queue and len(seen_sitemaps) < max_sitemaps and len(pages) < max_urls:
        url = queue.pop(0)
        if url in seen_sitemaps:
            continue
        seen_sitemaps.add(url)
        try:
            r = ghost.get(url, force="lite")
        except Exception:
            continue
        if not r.ok or not r.html:
            continue
        page_urls, nested = _parse_sitemap_xml(r.html, url)
        pages.extend(page_urls)
        queue.extend(u for u in nested if u not in seen_sitemaps)

    return pages[:max_urls]
