# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Shared Azure credential singleton for async contexts.

This module provides a single DefaultAzureCredential instance that can be
shared across all Azure SDK clients in the application, reducing token
acquisition overhead and improving startup time.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Callable, Coroutine

if TYPE_CHECKING:
    from azure.identity.aio import DefaultAzureCredential

logger = logging.getLogger(__name__)

# Lazy imports to avoid requiring azure-identity when not used
_DefaultAzureCredential: type[DefaultAzureCredential] | None = None
_get_bearer_token_provider: (
    Callable[..., Callable[[], Coroutine[Any, Any, str]]] | None
) = None

# Singleton state
_credential: DefaultAzureCredential | None = None
_lock = asyncio.Lock()


def _ensure_imports():
    """Lazily import Azure Identity SDK."""
    global _DefaultAzureCredential, _get_bearer_token_provider
    if _DefaultAzureCredential is None:
        from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider

        _DefaultAzureCredential = DefaultAzureCredential
        _get_bearer_token_provider = get_bearer_token_provider


async def get_azure_credential() -> DefaultAzureCredential:
    """
    Get the shared async DefaultAzureCredential singleton.

    This credential is lazily initialized on first call and reused for all
    subsequent calls. The credential handles token caching internally.

    Returns:
        DefaultAzureCredential: The shared credential instance.

    Example:
        credential = await get_azure_credential()
        client = SomeAzureClient(credential=credential)
    """
    global _credential

    async with _lock:
        if _credential is None:
            _ensure_imports()
            assert _DefaultAzureCredential is not None
            logger.info("Initializing shared Azure DefaultAzureCredential")
            _credential = _DefaultAzureCredential()
        return _credential


async def get_openai_token_provider(
    scope: str = "https://cognitiveservices.azure.com/.default",
) -> Callable[[], Coroutine[Any, Any, str]]:
    """
    Get an async token provider for Azure OpenAI clients.

    This wraps the shared credential in a token provider callable that can be
    passed to AsyncAzureOpenAI's azure_ad_token_provider parameter.

    Args:
        scope: The OAuth scope for the token. Defaults to Azure Cognitive Services.

    Returns:
        An async callable that returns a bearer token when awaited.

    Example:
        token_provider = await get_openai_token_provider()
        client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            azure_ad_token_provider=token_provider,
            api_version=api_version,
        )
    """
    _ensure_imports()
    assert _get_bearer_token_provider is not None
    credential = await get_azure_credential()
    return _get_bearer_token_provider(credential, scope)


async def close_credential() -> None:
    """
    Close the shared credential and release resources.

    Call this during application shutdown to properly clean up the credential.
    After calling this, get_azure_credential() will create a new instance.
    """
    global _credential

    async with _lock:
        if _credential is not None:
            logger.info("Closing shared Azure DefaultAzureCredential")
            await _credential.close()
            _credential = None
