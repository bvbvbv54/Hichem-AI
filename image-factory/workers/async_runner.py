from __future__ import annotations

import asyncio
from typing import TypeVar, Awaitable

T = TypeVar("T")


def run_async(coro: Awaitable[T]) -> T:
    """Run a coroutine from a synchronous Celery task context.
    Creates a new event loop per call to avoid conflicts.
    Never resets the global DB engine.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
