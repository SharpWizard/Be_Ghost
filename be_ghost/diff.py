"""HTML diff between two responses."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass


@dataclass
class HtmlDiff:
    added_lines: int
    removed_lines: int
    changed_text_chars: int
    unified: str  # full unified-diff string

    def __str__(self) -> str:
        return f"<HtmlDiff +{self.added_lines} -{self.removed_lines}, {self.changed_text_chars} text chars>"


def _normalize(html: str) -> list[str]:
    """Strip whitespace and split into lines for diffing."""
    h = re.sub(r">\s+<", ">\n<", html)
    return [line.strip() for line in h.splitlines() if line.strip()]


def _text_only(html: str) -> str:
    no_scripts = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", no_scripts)).strip()


def diff(a: str, b: str, *, context: int = 3) -> HtmlDiff:
    a_lines = _normalize(a)
    b_lines = _normalize(b)
    unified = "\n".join(difflib.unified_diff(a_lines, b_lines, n=context, lineterm=""))
    added = sum(1 for ln in unified.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in unified.splitlines() if ln.startswith("-") and not ln.startswith("---"))
    text_a = _text_only(a)
    text_b = _text_only(b)
    sm = difflib.SequenceMatcher(None, text_a, text_b)
    changed_chars = sum((j2 - j1) + (i2 - i1) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal")
    return HtmlDiff(added_lines=added, removed_lines=removed,
                    changed_text_chars=changed_chars, unified=unified)
