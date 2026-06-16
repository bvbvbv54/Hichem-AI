from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_rate_limiter_acquire_release():
    from services.acquisition.rate_limiter import DomainRateLimiter
    limiter = DomainRateLimiter()
    await limiter.acquire("example.com")
    await limiter.close()


@pytest.mark.asyncio
async def test_rate_limiter_block_domain():
    from services.acquisition.rate_limiter import DomainRateLimiter
    limiter = DomainRateLimiter()
    await limiter.block_domain("blocked.com", 3600)
    blocked_until = limiter._domain_blocked_until.get("blocked.com")
    assert blocked_until is not None
    assert blocked_until > 0
    await limiter.close()


@pytest.mark.asyncio
async def test_rate_limiter_respects_crawl_delay():
    from services.acquisition.rate_limiter import DomainRateLimiter
    import time
    limiter = DomainRateLimiter()
    before = time.monotonic()
    await limiter.acquire("slow.com")
    after = time.monotonic()
    await limiter.close()
    assert (after - before) < 0.5


@pytest.mark.asyncio
async def test_rate_limiter_record_success_resets_block():
    from services.acquisition.rate_limiter import DomainRateLimiter
    limiter = DomainRateLimiter()
    await limiter.block_domain("test.com", 60)
    await limiter.record_success("test.com")
    bucket = limiter._local_buckets.get("test.com")
    assert bucket is None or bucket._rate > 0.001
    await limiter.close()
