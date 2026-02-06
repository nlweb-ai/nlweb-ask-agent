# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Simple in-memory rate limiter for NLWeb server.

Uses token bucket algorithm with per-IP and per-user rate limiting.
"""

import asyncio
import logging
import time
from collections import defaultdict
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class TokenBucket:
    """Token bucket for rate limiting."""

    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket.

        Args:
            capacity: Maximum number of tokens
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
        self.lock = asyncio.Lock()

    async def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens were consumed, False if rate limit exceeded
        """
        async with self.lock:
            # Refill tokens based on time elapsed
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + (elapsed * self.refill_rate))
            self.last_refill = now

            # Try to consume tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            else:
                return False


class RateLimiter:
    """
    Rate limiter using token bucket algorithm.

    Supports per-IP and per-user rate limiting with configurable limits.
    """

    def __init__(self, requests_per_minute: int = 60, burst_size: int = 10):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Average requests allowed per minute
            burst_size: Maximum burst of requests allowed
        """
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.refill_rate = requests_per_minute / 60.0  # Tokens per second

        # Store buckets: {client_id: TokenBucket}
        self.buckets: Dict[str, TokenBucket] = {}
        self.lock = asyncio.Lock()

        # Cleanup task
        self._cleanup_task = None

        logger.info(
            f"Rate limiter initialized: {requests_per_minute} req/min, "
            f"burst={burst_size}"
        )

    def _get_or_create_bucket(self, client_id: str) -> TokenBucket:
        """Get existing bucket or create new one."""
        if client_id not in self.buckets:
            self.buckets[client_id] = TokenBucket(
                capacity=self.burst_size, refill_rate=self.refill_rate
            )
        return self.buckets[client_id]

    async def check_rate_limit(self, client_id: str) -> Tuple[bool, Dict[str, any]]:
        """
        Check if request is allowed under rate limit.

        Args:
            client_id: Unique identifier for client (IP or user_id)

        Returns:
            Tuple of (allowed, headers)
            - allowed: True if request is allowed
            - headers: Rate limit headers to include in response
        """
        async with self.lock:
            bucket = self._get_or_create_bucket(client_id)

        # Try to consume one token
        allowed = await bucket.consume(1)

        # Calculate rate limit headers
        headers = {
            "X-RateLimit-Limit": str(self.requests_per_minute),
            "X-RateLimit-Remaining": str(int(bucket.tokens)),
            "X-RateLimit-Reset": str(int(bucket.last_refill + 60)),
        }

        if not allowed:
            # Calculate retry-after in seconds
            tokens_needed = 1 - bucket.tokens
            retry_after = int(tokens_needed / self.refill_rate)
            headers["Retry-After"] = str(retry_after)
            # Sanitize client_id for logging to prevent log injection
            sanitized_client_id = client_id.replace("\n", "\\n").replace("\r", "\\r")
            logger.warning(f"Rate limit exceeded for {sanitized_client_id}")

        return allowed, headers

    async def cleanup_old_buckets(self):
        """Periodically remove inactive buckets to prevent memory leak."""
        while True:
            await asyncio.sleep(300)  # Cleanup every 5 minutes

            async with self.lock:
                now = time.time()
                # Remove buckets inactive for >10 minutes
                inactive_threshold = now - 600

                to_remove = [
                    client_id
                    for client_id, bucket in self.buckets.items()
                    if bucket.last_refill < inactive_threshold
                ]

                for client_id in to_remove:
                    del self.buckets[client_id]

                if to_remove:
                    logger.debug(
                        f"Cleaned up {len(to_remove)} inactive rate limit buckets"
                    )

    def start_cleanup_task(self):
        """Start background cleanup task."""
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self.cleanup_old_buckets())

    async def stop_cleanup_task(self):
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None


# Global rate limiter instance
_rate_limiter = None


def get_rate_limiter(
    requests_per_minute: int = 60, burst_size: int = 10
) -> RateLimiter:
    """
    Get or create global rate limiter instance.

    Args:
        requests_per_minute: Average requests allowed per minute
        burst_size: Maximum burst of requests allowed

    Returns:
        RateLimiter instance
    """
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(
            requests_per_minute=requests_per_minute, burst_size=burst_size
        )
        _rate_limiter.start_cleanup_task()
    return _rate_limiter


async def shutdown_rate_limiter():
    """Shutdown global rate limiter."""
    global _rate_limiter
    if _rate_limiter:
        await _rate_limiter.stop_cleanup_task()
        _rate_limiter = None
