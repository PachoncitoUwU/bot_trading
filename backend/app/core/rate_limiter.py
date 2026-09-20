"""Asynchronous Token Bucket Rate Limiter.
Prevents IP bans and API throttling by proactively spacing out exchange requests.
"""
import asyncio
import time
from typing import Optional


class AsyncTokenBucketRateLimiter:
    """
    Thread-safe and async-safe Token Bucket rate limiter.
    
    capacity: Maximum burst tokens available in the bucket.
    refill_rate: Tokens added per second (e.g. 20 tokens/sec = 1200 tokens/min).
    """

    def __init__(self, capacity: float = 50.0, refill_rate: float = 20.0):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    def get_current_tokens(self) -> float:
        """Returns the current token count accounting for elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_update
        return min(self.capacity, self.tokens + elapsed * self.refill_rate)

    async def acquire(self, weight: float = 1.0, timeout: Optional[float] = 10.0) -> bool:
        """
        Consumes `weight` tokens. If not enough tokens are available,
        asynchronously waits until enough tokens are replenished.
        """
        start_time = time.monotonic()

        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.last_update = now

                # Replenish tokens based on elapsed time
                self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)

                if self.tokens >= weight:
                    self.tokens -= weight
                    return True

                # Calculate how long we must wait
                needed = weight - self.tokens
                wait_time = needed / self.refill_rate

            if timeout is not None and (time.monotonic() - start_time + wait_time) > timeout:
                return False

            await asyncio.sleep(min(wait_time, 0.5))


# Global rate limiter instance for exchange communications
exchange_rate_limiter = AsyncTokenBucketRateLimiter(capacity=60.0, refill_rate=20.0)
