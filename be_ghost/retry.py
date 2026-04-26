"""Retry with exponential backoff + jitter."""

from __future__ import annotations

import asyncio
import random
import time
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


def retry_sync(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    factor: float = 2.0,
    jitter: float = 0.3,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Call fn up to `attempts` times with exponential backoff. Re-raises the final error."""
    delay = base_delay
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except retry_on as e:
            last = e
            if i == attempts - 1:
                break
            sleep = min(max_delay, delay) * (1 + random.uniform(-jitter, jitter))
            time.sleep(max(0.0, sleep))
            delay *= factor
    assert last is not None
    raise last


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    factor: float = 2.0,
    jitter: float = 0.3,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    delay = base_delay
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return await fn()
        except retry_on as e:
            last = e
            if i == attempts - 1:
                break
            sleep = min(max_delay, delay) * (1 + random.uniform(-jitter, jitter))
            await asyncio.sleep(max(0.0, sleep))
            delay *= factor
    assert last is not None
    raise last
