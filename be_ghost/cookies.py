"""Programmatic cookie editor for BeGhost.

    ghost.cookies.set("session", "abc", domain=".example.com")
    ghost.cookies.delete("session", domain=".example.com")
    ghost.cookies.list()
    ghost.cookies.clear()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .browser import BeGhost


class CookieEditor:
    def __init__(self, ghost: "BeGhost") -> None:
        self._ghost = ghost

    def _ctx(self):
        ctx = self._ghost._last_ctx
        if ctx is None:
            # create a context lazily so the user can edit cookies before any get()
            ctx = self._ghost._new_context()
        return ctx

    def set(self, name: str, value: str, *, domain: str = "", path: str = "/",
            expires: int | None = None, secure: bool = False, http_only: bool = False,
            same_site: str | None = None, url: str | None = None) -> None:
        cookie: dict[str, Any] = {"name": name, "value": value, "path": path}
        if url:
            cookie["url"] = url
        else:
            cookie["domain"] = domain
        if expires is not None:
            cookie["expires"] = expires
        if secure:
            cookie["secure"] = True
        if http_only:
            cookie["httpOnly"] = True
        if same_site:
            cookie["sameSite"] = same_site
        self._ctx().add_cookies([cookie])

    def list(self, urls: list[str] | None = None) -> list[dict]:
        return self._ctx().cookies(urls=urls) if urls else self._ctx().cookies()

    def delete(self, name: str, *, domain: str = "", path: str = "/") -> None:
        ctx = self._ctx()
        # Playwright doesn't have delete; clear and re-add the rest.
        keep = [c for c in ctx.cookies()
                if not (c.get("name") == name and (not domain or c.get("domain") == domain))]
        ctx.clear_cookies()
        if keep:
            ctx.add_cookies(keep)

    def clear(self) -> None:
        self._ctx().clear_cookies()
