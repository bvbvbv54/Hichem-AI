from __future__ import annotations

import asyncio
from typing import TypeVar, Awaitable

T = TypeVar("T")


def run_async(coro: Awaitable[T]) -> T:
    """Run a coroutine from a synchronous Celery task context.
    Creates a new event loop per call and sets it as current to
    avoid 'Event loop is closed' errors from aioredis in forked workers.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.close()
        except Exception:
            pass
        asyncio.set_event_loop(None)
