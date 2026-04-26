"""Extract structured metadata from a page: title, description, OpenGraph,
Twitter Cards, JSON-LD, canonical URL."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PageMetadata:
    title: str = ""
    description: str = ""
    canonical: str = ""
    og: dict[str, str] = field(default_factory=dict)
    twitter: dict[str, str] = field(default_factory=dict)
    jsonld: list[Any] = field(default_factory=list)
    images: list[str] = field(default_factory=list)


_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_META = re.compile(r"<meta\s+([^>]+?)/?>", re.I)
_LINK = re.compile(r"<link\s+([^>]+?)/?>", re.I)
_ATTR = re.compile(r'(\w[\w-]*)\s*=\s*"([^"]*)"|(\w[\w-]*)\s*=\s*\'([^\']*)\'')
_JSONLD = re.compile(
    r'<script[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)


def _attrs(s: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _ATTR.finditer(s):
        k = (m.group(1) or m.group(3) or "").lower()
        v = m.group(2) if m.group(2) is not None else (m.group(4) or "")
        if k:
            out[k] = v
    return out


def extract(html: str) -> PageMetadata:
    md = PageMetadata()

    m = _TITLE.search(html)
    if m:
        md.title = re.sub(r"\s+", " ", m.group(1)).strip()

    for tag in _META.findall(html):
        a = _attrs(tag)
        prop = a.get("property", "").lower()
        name = a.get("name", "").lower()
        content = a.get("content", "")
        if not content:
            continue
        if prop.startswith("og:"):
            md.og[prop[3:]] = content
            if prop == "og:image":
                md.images.append(content)
        elif name == "description":
            md.description = content
        elif name.startswith("twitter:"):
            md.twitter[name[8:]] = content

    if not md.description and md.og.get("description"):
        md.description = md.og["description"]

    for tag in _LINK.findall(html):
        a = _attrs(tag)
        if a.get("rel", "").lower() == "canonical" and a.get("href"):
            md.canonical = a["href"]
            break

    for block in _JSONLD.findall(html):
        try:
            md.jsonld.append(json.loads(block.strip()))
        except json.JSONDecodeError:
            continue

    return md
