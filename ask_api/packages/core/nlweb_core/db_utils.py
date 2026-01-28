# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Database utility functions including retry logic for transient failures.
"""

import asyncio
import logging
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger(__name__)


def with_db_retry(max_retries: int = 3, initial_backoff: float = 0.5, max_backoff: float = 10.0):
    """
    Decorator that adds retry logic with exponential backoff for database operations.

    Retries on transient database errors like connection failures, timeouts, etc.
    Uses exponential backoff: wait_time = initial_backoff * (2 ** attempt)

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        initial_backoff: Initial backoff time in seconds (default: 0.5)
        max_backoff: Maximum backoff time in seconds (default: 10.0)

    Usage:
        @with_db_retry(max_retries=3, initial_backoff=0.5)
        async def store_message(self, message):
            # ... database operation ...

    Example:
        Attempt 1 fails -> wait 0.5s
        Attempt 2 fails -> wait 1.0s
        Attempt 3 fails -> wait 2.0s
        Attempt 4 fails -> raise exception
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    # Try the operation
                    return await func(*args, **kwargs)

                except Exception as e:
                    last_exception = e

                    # Check if this is a transient error worth retrying
                    is_transient = _is_transient_error(e)

                    # Don't retry on last attempt or non-transient errors
                    if attempt >= max_retries or not is_transient:
                        if not is_transient:
                            logger.error(f"{func.__name__} failed with non-transient error: {e}")
                        else:
                            logger.error(f"{func.__name__} failed after {max_retries + 1} attempts: {e}")
                        raise

                    # Calculate backoff time with exponential growth
                    wait_time = min(initial_backoff * (2 ** attempt), max_backoff)

                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {wait_time:.1f}s: {e}"
                    )

                    # Wait before retrying
                    await asyncio.sleep(wait_time)

            # This should never be reached, but just in case
            raise last_exception

        return wrapper
    return decorator


def _is_transient_error(error: Exception) -> bool:
    """
    Determine if an error is transient and worth retrying.

    Transient errors include:
    - Connection errors
    - Timeout errors
    - Network errors
    - Some database lock errors

    Non-transient errors include:
    - Data validation errors
    - Constraint violations
    - Authentication failures

    Args:
        error: The exception to check

    Returns:
        True if error is likely transient, False otherwise
    """
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()

    # Transient error patterns
    transient_patterns = [
        'connection',
        'timeout',
        'network',
        'broken pipe',
        'connection reset',
        'connection refused',
        'too many connections',
        'pool',
        'deadlock',
        'lock timeout',
        'server closed the connection',
        'cannot connect',
        'could not connect',
        'no route to host',
        'temporary failure',
    ]

    # Check for asyncpg-specific transient errors
    try:
        import asyncpg
        if isinstance(error, (
            asyncpg.TooManyConnectionsError,
            asyncpg.ConnectionDoesNotExistError,
            asyncpg.CannotConnectNowError,
            asyncpg.ConnectionRejectionError,
        )):
            return True
    except ImportError:
        pass

    # Check for general connection/timeout errors
    if isinstance(error, (
        ConnectionError,
        ConnectionRefusedError,
        ConnectionResetError,
        BrokenPipeError,
        TimeoutError,
        asyncio.TimeoutError,
        OSError,
    )):
        return True

    # Check error message for transient patterns
    for pattern in transient_patterns:
        if pattern in error_str or pattern in error_type:
            return True

    # Non-transient error patterns (explicitly not retryable)
    non_transient_patterns = [
        'constraint',
        'unique',
        'foreign key',
        'null value',
        'invalid',
        'permission',
        'denied',
        'authentication',
        'syntax error',
        'column',
        'table',
        'does not exist',
    ]

    for pattern in non_transient_patterns:
        if pattern in error_str:
            return False

    # Default: assume non-transient to avoid infinite retries on unknown errors
    return False
