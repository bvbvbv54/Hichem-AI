from __future__ import annotations

import asyncio
import json

import redis.asyncio as aioredis
from fastapi import APIRouter, Query
from starlette.responses import StreamingResponse

from configs.logging import get_logger
from configs.settings import settings

logger = get_logger(__name__)

router = APIRouter(prefix="/events", tags=["Events"])

CHANNEL = "events"


async def event_generator(token: str):
    """Generate server-sent events from Redis pub/sub with robust error handling."""
    r = None
    pubsub = None
    try:
        # Connect to Redis with timeout
        r = await asyncio.wait_for(
            aioredis.from_url(settings.redis_url, socket_connect_timeout=5),
            timeout=10.0
        )
        pubsub = r.pubsub()
        await pubsub.subscribe(CHANNEL)

        # Send initial connection confirmation
        yield f": Connected to event stream\n\n"

        while True:
            try:
                # Get message with timeout to send periodic heartbeats
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=30.0
                )
                
                if message and message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    try:
                        parsed = json.loads(data)
                        event_type = parsed.get("type", "job_update")
                        yield f"event: {event_type}\ndata: {data}\n\n"
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse event data", extra={"data": data})
                else:
                    # Send heartbeat to keep connection alive
                    yield f": heartbeat\n\n"
            except asyncio.TimeoutError:
                # Send heartbeat on timeout
                yield f": heartbeat\n\n"

    except asyncio.TimeoutError:
        logger.warning("SSE: Redis connection timeout")
        yield f": error: Redis connection timeout\n\n"
    except Exception as e:
        logger.error("SSE: Error in event generator", exc_info=True)
        yield f": error: {str(e)}\n\n"
    finally:
        # Cleanup
        try:
            if pubsub:
                await pubsub.unsubscribe(CHANNEL)
                await pubsub.close()
            if r:
                await r.aclose()
        except Exception as e:
            logger.warning("SSE: Error during cleanup", exc_info=True)


@router.get("")
async def sse_events(token: str = Query("")):
    """Server-Sent Events endpoint for real-time updates."""
    try:
        return StreamingResponse(
            event_generator(token),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Transfer-Encoding": "chunked",
            },
        )
    except Exception as e:
        logger.error("SSE: Error creating stream", exc_info=True)
        return StreamingResponse(
            (f": error: {str(e)}\n\n" for _ in [None]),
            media_type="text/event-stream",
            status_code=500,
        )

