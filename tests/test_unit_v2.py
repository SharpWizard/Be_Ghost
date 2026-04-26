"""Unit tests for the new modules: extract, diff, consent selectors."""

from __future__ import annotations

import pytest

from be_ghost.diff import _normalize as _diff_normalize, diff
from be_ghost.extract import extract_from_html


# ---------- extraction templates --------------------------------------------

class TestExtract:
    HTML = """
    <html><body>
      <h1>Cool Product</h1>
      <span class="price">$ 49.99</span>
      <ul class="tags">
        <li>red</li><li>cotton</li><li>summer</li>
      </ul>
      <img class="gallery" src="/a.png">
      <img class="gallery" src="/b.png">
      <a href="/buy">Buy</a>
    </body></html>
    """

    def test_simple_text(self):
        out = extract_from_html(self.HTML, {"title": "h1"})
        assert out == {"title": "Cool Product"}

    def test_typed_float(self):
        out = extract_from_html(self.HTML, {"price": (".price", "float")})
        assert out["price"] == 49.99

    def test_typed_int(self):
        out = extract_from_html("<span>$1,200 USD</span>", {"x": ("span", "int")})
        assert out["x"] == 1200

    def test_attr_first(self):
        out = extract_from_html(self.HTML, {"img": ("img.gallery", "src")})
        assert out["img"] == "/a.png"

    def test_attr_all(self):
        out = extract_from_html(self.HTML, {"imgs": ("img.gallery", "src", "all")})
        assert out["imgs"] == ["/a.png", "/b.png"]

    def test_text_all(self):
        out = extract_from_html(self.HTML, {"tags": ("ul.tags > li", "text", "all")})
        assert out["tags"] == ["red", "cotton", "summer"]

    def test_request_url_passthrough(self):
        out = extract_from_html("<html></html>", {"u": "@request"}, request_url="https://x.com")
        assert out["u"] == "https://x.com"

    def test_missing_returns_none(self):
        out = extract_from_html("<html></html>", {"x": "h99"})
        assert out["x"] is None

    def test_invalid_rule_raises(self):
        with pytest.raises(ValueError):
            extract_from_html("<html></html>", {"x": 42})  # type: ignore[dict-item]


# ---------- HTML diff -------------------------------------------------------

class TestDiff:
    def test_identical(self):
        d = diff("<p>hi</p>", "<p>hi</p>")
        assert d.added_lines == 0 and d.removed_lines == 0
        assert d.changed_text_chars == 0

    def test_added_line(self):
        a = "<p>one</p><p>two</p>"
        b = "<p>one</p><p>two</p><p>three</p>"
        d = diff(a, b)
        assert d.added_lines >= 1

    def test_text_changed_chars(self):
        a = "<p>old text</p>"
        b = "<p>new text</p>"
        d = diff(a, b)
        assert d.changed_text_chars > 0
        assert "+" in d.unified
        assert "-" in d.unified

    def test_normalize_strips_whitespace(self):
        lines = _diff_normalize("  <a>  </a>  \n\n  <b>x</b>  ")
        assert lines == ["<a>", "</a>", "<b>x</b>"]

    def test_repr(self):
        d = diff("<a/>", "<b/>")
        assert "HtmlDiff" in str(d)


# ---------- consent selectors ----------------------------------------------

class TestConsentSelectors:
    def test_table_well_formed(self):
        from be_ghost.consent import SELECTORS
        assert SELECTORS, "selectors table is empty"
        for name, sels in SELECTORS:
            assert isinstance(name, str) and name
            assert isinstance(sels, list) and sels
            for s in sels:
                assert isinstance(s, str) and s

    def test_includes_major_providers(self):
        from be_ghost.consent import SELECTORS
        names = {n for n, _ in SELECTORS}
        for must_have in ("onetrust", "cookiebot", "didomi", "quantcast"):
            assert must_have in names
