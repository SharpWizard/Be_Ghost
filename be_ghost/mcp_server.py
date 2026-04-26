"""MCP server exposing Be_Ghost as tools for LLM clients.

Run via:
    be_ghost_mcp                    # console script (after pip install)
    python -m be_ghost.mcp_server   # also works

Configure in Claude Desktop / Claude Code:
    {
      "mcpServers": {
        "be_ghost": { "command": "be_ghost_mcp" }
      }
    }

Tools exposed:
    fetch(url, profile?, lite?, wait_for?, output?) -> str
    screenshot(url, path?, full_page?) -> str
    extract(url, css) -> list[str]
    submit_form(url, fields, submit?) -> str
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from typing import Any

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool
except ImportError:
    Server = None  # type: ignore[assignment]


SERVER_NAME = "be_ghost"
SERVER_VERSION = "0.3.0"


def _build_server():
    from .async_browser import AsyncBeGhost

    server = Server(SERVER_NAME)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="fetch",
                description="Fetch a URL through Be_Ghost (stealth Chromium). Returns HTML, JSON, or text.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "profile": {"type": "string", "description": "win11_chrome | mac_chrome | linux_chrome | win10_chrome"},
                        "lite": {"type": "boolean", "default": True},
                        "wait_for": {"type": "string", "description": "CSS selector to wait for"},
                        "output": {"type": "string", "enum": ["html", "text", "json", "info"], "default": "html"},
                    },
                    "required": ["url"],
                },
            ),
            Tool(
                name="screenshot",
                description="Capture a full-page screenshot of a URL. Returns the path to the PNG.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "path": {"type": "string", "description": "output path; default: temp file"},
                        "full_page": {"type": "boolean", "default": True},
                    },
                    "required": ["url"],
                },
            ),
            Tool(
                name="extract",
                description="Fetch a URL and return text from elements matching a CSS selector (requires selectolax).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "css": {"type": "string"},
                        "limit": {"type": "integer", "default": 50},
                    },
                    "required": ["url", "css"],
                },
            ),
            Tool(
                name="submit_form",
                description="Open a URL, fill a form (selector→value mapping), optionally click submit, return resulting HTML.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "fields": {"type": "object", "additionalProperties": {"type": "string"}},
                        "submit": {"type": "string", "description": "CSS selector to click after fill"},
                    },
                    "required": ["url", "fields"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "fetch":
            return await _fetch(arguments)
        if name == "screenshot":
            return await _screenshot(arguments)
        if name == "extract":
            return await _extract(arguments)
        if name == "submit_form":
            return await _submit_form(arguments)
        return [TextContent(type="text", text=f"unknown tool: {name}")]

    async def _fetch(a: dict) -> list[TextContent]:
        async with AsyncBeGhost(
            profile=a.get("profile"),
            lite=a.get("lite", True),
        ) as ghost:
            r = await ghost.get(a["url"], wait_for=a.get("wait_for"))
            output = a.get("output", "html")
            if output == "info":
                cap = r.captcha
                body = json.dumps({
                    "status": r.status, "final_url": r.final_url,
                    "elapsed_ms": r.elapsed_ms, "size": len(r.html),
                    "captcha": cap.kind if cap.detected else None,
                    "profile": ghost.profile.get("name"),
                }, indent=2)
            elif output == "json":
                try:
                    body = json.dumps(r.json(), indent=2)
                except Exception:
                    body = r.html
            elif output == "text":
                try:
                    body = r.text_only()
                except ImportError:
                    body = r.html
            else:
                body = r.html
            return [TextContent(type="text", text=body)]

    async def _screenshot(a: dict) -> list[TextContent]:
        path = a.get("path") or os.path.join(tempfile.gettempdir(), "be_ghost_screenshot.png")
        async with AsyncBeGhost(lite=False) as ghost:
            await ghost.get(a["url"], screenshot=path)
        return [TextContent(type="text", text=f"screenshot saved: {path}")]

    async def _extract(a: dict) -> list[TextContent]:
        async with AsyncBeGhost() as ghost:
            r = await ghost.get(a["url"])
            try:
                results = r.select_text(a["css"])[: a.get("limit", 50)]
            except ImportError:
                return [TextContent(type="text", text="selectolax not installed (pip install 'be_ghost[parse]')")]
        return [TextContent(type="text", text=json.dumps(results, indent=2))]

    async def _submit_form(a: dict) -> list[TextContent]:
        from .humanize import AsyncHumanPage
        async with AsyncBeGhost(lite=False) as ghost:
            async with ghost.session(a["url"], human=True) as page:
                assert isinstance(page, AsyncHumanPage)
                await page.fill_form(a["fields"], submit=a.get("submit"))
                await page.page.wait_for_load_state("domcontentloaded")
                html = await page.page.content()
        return [TextContent(type="text", text=html)]

    return server


def main() -> int:
    if Server is None:
        print("error: mcp package not installed. install with: pip install 'be_ghost[mcp]'")
        return 1

    async def run():
        server = _build_server()
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
