"""pytest plugin: provides `ghost` and `async_ghost` fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def ghost():
    """Session-scoped BeGhost. Single browser process for the test suite."""
    from .browser import BeGhost
    g = BeGhost()
    g.start()
    yield g
    g.close()


@pytest.fixture
def ghost_session(ghost):
    """Per-test interactive Page. Yielded as a real Playwright Page."""
    with ghost.session() as page:
        yield page


# async_ghost fixture is registered only if pytest-asyncio is installed.
try:
    import pytest_asyncio  # type: ignore[import-not-found]

    @pytest_asyncio.fixture(scope="session")
    async def async_ghost():
        """Session-scoped AsyncBeGhost."""
        from .async_browser import AsyncBeGhost
        g = AsyncBeGhost()
        await g.start()
        yield g
        await g.close()
except ImportError:
    pass
