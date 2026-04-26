"""Optional QuickJS sandbox for evaluating JS expressions outside a real browser.

Useful for:
  - Decoding obfuscated tokens / inline JS ciphers
  - Running standalone calculations that don't touch DOM/network
  - Evaluating simple page expressions like `document.title` against the parsed DOM

Not useful for:
  - Running real site bot-detection JS (would need full window/document/timing/canvas)
  - Anything async, fetch-driven, or canvas/WebGL

If the goal is to defeat real bot challenges, fall back to BeGhost(mode='full').
"""

from __future__ import annotations

from typing import Any


def available() -> bool:
    try:
        import quickjs  # type: ignore[import-not-found]  # noqa: F401
        return True
    except ImportError:
        return False


class LiteJS:
    """Thin wrapper around QuickJS with minimal browser-like globals."""

    def __init__(self) -> None:
        try:
            import quickjs  # type: ignore[import-not-found]
        except ImportError as e:
            raise ImportError(
                "quickjs not installed. install with: pip install 'be_ghost[lite]'"
            ) from e
        self._ctx = quickjs.Context()
        # Minimal stubs — enough for decoders, not for site detection scripts.
        self._ctx.eval(
            "var window = {};"
            "var globalThis = window;"
            "var navigator = {userAgent: ''};"
            "var location = {href: ''};"
            "var document = {title: '', cookie: ''};"
        )

    def eval(self, code: str) -> Any:
        return self._ctx.eval(code)

    def eval_in_page(self, expr: str, tree, url: str) -> Any:
        """Evaluate `expr` with `document.title` and `location.href` set from the parsed tree."""
        title_node = tree.css_first("title")
        title = title_node.text(strip=True) if title_node else ""
        # Cheap, safe injection — string literals only.
        self._ctx.eval(f"document.title = {self._js_str(title)}; location.href = {self._js_str(url)};")
        return self._ctx.eval(expr)

    @staticmethod
    def _js_str(s: str) -> str:
        # JSON-encode to safely embed as a JS string.
        import json
        return json.dumps(s)
