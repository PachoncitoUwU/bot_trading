"""Unit Tests for Async Token Bucket Rate Limiter."""
import asyncio
import pytest
from app.core.rate_limiter import AsyncTokenBucketRateLimiter


@pytest.mark.asyncio
async def test_token_bucket_acquire_within_capacity():
    limiter = AsyncTokenBucketRateLimiter(capacity=10.0, refill_rate=5.0)
    # Should instantly acquire without wait
    success = await limiter.acquire(weight=5.0, timeout=1.0)
    assert success is True
    assert limiter.tokens <= 5.0


@pytest.mark.asyncio
async def test_token_bucket_refills_over_time():
    limiter = AsyncTokenBucketRateLimiter(capacity=5.0, refill_rate=10.0)
    await limiter.acquire(weight=5.0)
    assert limiter.tokens < 1.0

    # Wait for refill
    await asyncio.sleep(0.3)
    # Refill rate 10/sec * 0.3s = ~3 tokens replenished
    assert limiter.tokens >= 2.0
