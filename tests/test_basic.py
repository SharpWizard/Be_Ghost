"""Smoke tests using the be_ghost pytest fixtures."""

import pytest


def test_fetch_example(ghost):
    r = ghost.get("https://example.com", wait_until="domcontentloaded")
    assert r.ok
    assert "Example Domain" in r.html


def test_response_helpers(ghost):
    r = ghost.get("https://example.com", wait_until="domcontentloaded")
    assert r.text == r.html
    assert not r.captcha


@pytest.mark.asyncio
async def test_async_fetch(async_ghost):
    r = await async_ghost.get("https://example.com")
    assert r.ok
