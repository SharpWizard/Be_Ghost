"""Declarative extraction templates.

Turn a CSS-selector dict into structured data:

    page.extract({
        "title": "h1",
        "price": (".price", "float"),       # CSS + type coercion
        "images": ("img.gallery", "src"),    # multi-match → list of attrs
        "tags":   ("ul.tags > li", "text"),
        "url":    "@request",                # special: fetched URL
    })
"""

from __future__ import annotations

import re
from typing import Any

# Spec forms:
#   "h1"                          → first match's text content
#   ("h1", "text")                → first match's text content (explicit)
#   (".price", "float")           → first match, coerced to float
#   ("img.x", "src")              → first match's @src
#   ("img.x", "src", "all")       → list of @src across all matches
#   ("li.tag", "text", "all")     → list of text content
#   "@request"                    → the request URL (if available)


_TYPE_COERCERS = {
    "text": lambda s: s,
    "int": lambda s: int(re.sub(r"[^\d-]", "", s) or "0"),
    "float": lambda s: float(re.sub(r"[^\d.-]", "", s) or "0"),
    "bool": lambda s: bool(s and s.strip()),
}


def _coerce(raw: str | None, kind: str) -> Any:
    if raw is None:
        return None
    if kind in _TYPE_COERCERS:
        try:
            return _TYPE_COERCERS[kind](raw)
        except Exception:
            return None
    return raw


def _attr_or_text(node, what: str) -> str | None:
    if node is None:
        return None
    if what in ("text", "int", "float", "bool"):
        return node.text(separator=" ", strip=True) if hasattr(node, "text") else None
    if hasattr(node, "attributes"):
        return node.attributes.get(what)
    if hasattr(node, "get_attribute"):
        return node.get_attribute(what)
    return None


def extract_from_tree(tree, spec: dict[str, Any], *, request_url: str | None = None) -> dict[str, Any]:
    """Apply a template against a selectolax tree. Returns a flat dict."""
    out: dict[str, Any] = {}
    for key, rule in spec.items():
        if rule == "@request":
            out[key] = request_url
            continue
        css, what, mode = _normalize(rule)
        if mode == "all":
            nodes = tree.css(css)
            out[key] = [_coerce(_attr_or_text(n, what), what) for n in nodes]
            out[key] = [v for v in out[key] if v is not None]
        else:
            node = tree.css_first(css)
            out[key] = _coerce(_attr_or_text(node, what), what)
    return out


def _normalize(rule) -> tuple[str, str, str]:
    """Normalize a rule into (css, what, mode)."""
    if isinstance(rule, str):
        return rule, "text", "first"
    if isinstance(rule, tuple):
        if len(rule) == 1:
            return rule[0], "text", "first"
        if len(rule) == 2:
            return rule[0], rule[1], "first"
        if len(rule) >= 3:
            return rule[0], rule[1], rule[2]
    raise ValueError(f"invalid extraction rule: {rule!r}")


def extract_from_html(html: str, spec: dict[str, Any], *, request_url: str | None = None) -> dict[str, Any]:
    """Convenience: parse HTML then apply spec."""
    try:
        from selectolax.parser import HTMLParser
    except ImportError as e:
        raise ImportError("selectolax not installed (pip install 'be_ghost[parse]')") from e
    return extract_from_tree(HTMLParser(html), spec, request_url=request_url)
