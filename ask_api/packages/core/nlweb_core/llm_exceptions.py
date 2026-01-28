# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Custom exceptions for LLM operations.
Allows callers to distinguish between different types of LLM failures.
"""


class LLMError(Exception):
    """Base exception for all LLM-related errors."""
    pass


class LLMTimeoutError(LLMError):
    """LLM request timed out."""
    pass


class LLMAuthenticationError(LLMError):
    """LLM authentication failed (invalid API key, credentials, etc.)."""
    pass


class LLMRateLimitError(LLMError):
    """LLM rate limit exceeded."""
    pass


class LLMConnectionError(LLMError):
    """LLM connection failed (network error, service unavailable, etc.)."""
    pass


class LLMInvalidRequestError(LLMError):
    """LLM request was invalid (bad parameters, malformed prompt, etc.)."""
    pass


class LLMProviderError(LLMError):
    """LLM provider returned an error response."""
    pass


class LLMValidationError(LLMError):
    """LLM response failed Pydantic validation."""
    def __init__(self, message: str, raw_response: dict, validation_error: Exception):
        super().__init__(message)
        self.raw_response = raw_response
        self.validation_error = validation_error

    def __repr__(self) -> str:
        return f"LLMValidationError({self.args[0]!r}, raw_response={self.raw_response!r})"


def classify_llm_error(error: Exception) -> Exception:
    """
    Classify a generic exception into a specific LLM exception type.

    Args:
        error: The original exception

    Returns:
        A more specific LLM exception if classification is possible,
        otherwise wraps in generic LLMError
    """
    import asyncio

    error_str = str(error).lower()
    error_type = type(error).__name__.lower()

    # Timeout errors
    if isinstance(error, (asyncio.TimeoutError, TimeoutError)):
        return LLMTimeoutError(f"LLM request timed out: {error}")

    # Authentication errors
    auth_patterns = [
        'authentication', 'unauthorized', '401', 'invalid api key',
        'invalid_api_key', 'api_key', 'credentials', 'permission denied',
        'access denied', 'forbidden', '403'
    ]
    if any(pattern in error_str for pattern in auth_patterns):
        return LLMAuthenticationError(f"LLM authentication failed: {error}")

    # Rate limit errors
    rate_limit_patterns = [
        'rate limit', 'rate_limit', 'quota', 'too many requests',
        '429', 'throttl', 'requests per'
    ]
    if any(pattern in error_str for pattern in rate_limit_patterns):
        return LLMRateLimitError(f"LLM rate limit exceeded: {error}")

    # Connection errors
    connection_patterns = [
        'connection', 'network', 'timeout', 'unreachable',
        'service unavailable', '503', '502', 'bad gateway',
        'cannot connect', 'failed to connect'
    ]
    if any(pattern in error_str for pattern in connection_patterns):
        return LLMConnectionError(f"LLM connection failed: {error}")

    # Invalid request errors
    invalid_patterns = [
        'invalid', 'bad request', '400', 'malformed',
        'validation', 'missing required', 'parameter'
    ]
    if any(pattern in error_str for pattern in invalid_patterns):
        return LLMInvalidRequestError(f"LLM request invalid: {error}")

    # Provider-specific errors (500, etc.)
    provider_patterns = [
        'internal server error', '500', 'server error',
        'service error', 'provider error'
    ]
    if any(pattern in error_str for pattern in provider_patterns):
        return LLMProviderError(f"LLM provider error: {error}")

    # Default: generic LLM error
    return LLMError(f"LLM request failed: {error}")
