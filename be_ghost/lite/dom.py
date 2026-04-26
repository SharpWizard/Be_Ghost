"""DOM wrapper that mimics a Playwright Page using selectolax.

LitePage gives you the most-used Page API surface (locator, query_selector,
text_content, content, title, goto, fill, click on forms) without launching
a browser. Things that need a real engine (canvas, JS event loop, animations,
true clicks on JS handlers) are NOT supported and will raise.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin


def _need_selectolax():
    try:
        from selectolax.parser import HTMLParser
        return HTMLParser
    except ImportError as e:
        raise ImportError(
            "selectolax not installed. install with: pip install 'be_ghost[lite]'"
        ) from e


class LiteLocator:
    """Mini Playwright-style locator over a selectolax tree."""

    def __init__(self, page: "LitePage", css: str) -> None:
        self._page = page
        self._css = css

    def _nodes(self):
        return self._page._tree.css(self._css)

    @property
    def first(self) -> "LiteLocator":
        return self

    def count(self) -> int:
        return len(self._nodes())

    def text_content(self) -> str | None:
        n = self._page._tree.css_first(self._css)
        return n.text(separator=" ", strip=True) if n else None

    def inner_text(self) -> str:
        return self.text_content() or ""

    def inner_html(self) -> str:
        n = self._page._tree.css_first(self._css)
        return n.html or "" if n else ""

    def get_attribute(self, name: str) -> str | None:
        n = self._page._tree.css_first(self._css)
        return n.attributes.get(name) if n else None

    def all_text_contents(self) -> list[str]:
        return [n.text(separator=" ", strip=True) for n in self._nodes()]

    def click(self) -> None:
        # Only meaningful for <a href> and form submits.
        n = self._page._tree.css_first(self._css)
        if not n:
            raise RuntimeError(f"locator not found: {self._css}")
        tag = (n.tag or "").lower()
        href = n.attributes.get("href")
        if tag == "a" and href:
            self._page.goto(urljoin(self._page.url, href))
            return
        if tag in ("button", "input"):
            form = n.parent
            while form and (form.tag or "").lower() != "form":
                form = form.parent
            if form is not None:
                self._page._submit_form(form)
                return
        raise NotImplementedError(
            f"LiteLocator.click() on <{tag}> requires JS execution. "
            "Use mode='full' or run inside a session(human=True) on BeGhost."
        )

    def fill(self, value: str) -> None:
        # In lite mode, fill stages a value to be sent on the next form submit.
        n = self._page._tree.css_first(self._css)
        if not n:
            raise RuntimeError(f"locator not found: {self._css}")
        name = n.attributes.get("name")
        if not name:
            raise RuntimeError(f"input has no name attr: {self._css}")
        self._page._form_state[name] = value


class LitePage:
    """Page-like view over an HTTP response. Stateful: keeps cookies via the client."""

    def __init__(self, client, url: str, html: str, response) -> None:
        HTMLParser = _need_selectolax()
        self._client = client
        self.url = url
        self._html = html
        self._tree = HTMLParser(html)
        self._response = response
        self._form_state: dict[str, str] = {}

    # ---- read-only API matching Playwright Page ----------------------------

    def content(self) -> str:
        return self._html

    def title(self) -> str:
        n = self._tree.css_first("title")
        return n.text(strip=True) if n else ""

    def locator(self, css: str) -> LiteLocator:
        return LiteLocator(self, css)

    def query_selector(self, css: str) -> LiteLocator | None:
        return LiteLocator(self, css) if self._tree.css_first(css) else None

    def query_selector_all(self, css: str) -> list[LiteLocator]:
        return [LiteLocator(self, css)] if self._tree.css(css) else []

    def text_content(self, css: str) -> str | None:
        return LiteLocator(self, css).text_content()

    def inner_text(self, css: str) -> str:
        return LiteLocator(self, css).inner_text()

    def get_attribute(self, css: str, name: str) -> str | None:
        return LiteLocator(self, css).get_attribute(name)

    # ---- navigation --------------------------------------------------------

    def goto(self, url: str) -> "LitePage":
        absolute = url if "://" in url else urljoin(self.url, url)
        result = self._client.get(absolute)
        self.url = result.final_url
        self._html = result.text
        self._tree = _need_selectolax()(result.text)
        self._response = result
        self._form_state.clear()
        return self

    def fill(self, css: str, value: str) -> None:
        LiteLocator(self, css).fill(value)

    def evaluate(self, expr: str) -> Any:
        """Evaluate a JS expression in the optional QuickJS sandbox."""
        from .js import LiteJS
        js = LiteJS()
        return js.eval_in_page(expr, self._tree, self.url)

    # ---- form submit (used by Locator.click on <button>) -------------------

    def _submit_form(self, form_node) -> None:
        action = form_node.attributes.get("action") or self.url
        method = (form_node.attributes.get("method") or "GET").upper()
        target = action if "://" in action else urljoin(self.url, action)

        # collect inputs from the tree (not just _form_state)
        data: dict[str, str] = {}
        for inp in form_node.css("input, textarea, select"):
            name = inp.attributes.get("name")
            if not name:
                continue
            data[name] = self._form_state.get(name, inp.attributes.get("value", ""))

        if method == "GET":
            from urllib.parse import urlencode, urlparse, urlunparse
            parts = list(urlparse(target))
            existing = parts[4]
            parts[4] = urlencode(data) if not existing else f"{existing}&{urlencode(data)}"
            result = self._client.get(urlunparse(parts))
        else:
            result = self._client.post(target, data=data)

        self.url = result.final_url
        self._html = result.text
        self._tree = _need_selectolax()(result.text)
        self._response = result
        self._form_state.clear()

    # ---- extraction --------------------------------------------------------

    def extract(self, spec: dict) -> dict:
        from ..extract import extract_from_tree
        return extract_from_tree(self._tree, spec, request_url=self.url)

    # ---- raw access --------------------------------------------------------

    @property
    def html(self) -> str:
        return self._html

    @property
    def status(self) -> int:
        return self._response.status if self._response else 0


class AsyncLitePage:
    """Async variant of LitePage. Same DOM API; navigation/submit are async."""

    def __init__(self, client, url: str, html: str, response) -> None:
        HTMLParser = _need_selectolax()
        self._client = client
        self.url = url
        self._html = html
        self._tree = HTMLParser(html)
        self._response = response
        self._form_state: dict[str, str] = {}

    def content(self) -> str:
        return self._html

    def title(self) -> str:
        n = self._tree.css_first("title")
        return n.text(strip=True) if n else ""

    def locator(self, css: str) -> LiteLocator:
        return LiteLocator(self, css)  # type: ignore[arg-type]

    def query_selector(self, css: str) -> LiteLocator | None:
        return LiteLocator(self, css) if self._tree.css_first(css) else None  # type: ignore[arg-type]

    def query_selector_all(self, css: str) -> list[LiteLocator]:
        return [LiteLocator(self, css)] if self._tree.css(css) else []  # type: ignore[arg-type]

    def text_content(self, css: str) -> str | None:
        return LiteLocator(self, css).text_content()  # type: ignore[arg-type]

    def inner_text(self, css: str) -> str:
        return LiteLocator(self, css).inner_text()  # type: ignore[arg-type]

    def get_attribute(self, css: str, name: str) -> str | None:
        return LiteLocator(self, css).get_attribute(name)  # type: ignore[arg-type]

    async def goto(self, url: str) -> "AsyncLitePage":
        absolute = url if "://" in url else urljoin(self.url, url)
        result = await self._client.get(absolute)
        self.url = result.final_url
        self._html = result.text
        self._tree = _need_selectolax()(result.text)
        self._response = result
        self._form_state.clear()
        return self

    def fill(self, css: str, value: str) -> None:
        n = self._tree.css_first(css)
        if not n:
            raise RuntimeError(f"locator not found: {css}")
        name = n.attributes.get("name")
        if not name:
            raise RuntimeError(f"input has no name attr: {css}")
        self._form_state[name] = value

    @property
    def html(self) -> str:
        return self._html

    @property
    def status(self) -> int:
        return self._response.status if self._response else 0
