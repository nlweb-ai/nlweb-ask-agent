# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Wrapper around the various embedding providers.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

from typing import Optional, List
import asyncio
import threading

from nlweb_core.config import get_config


# Add locks for thread-safe provider access
_provider_locks = {
    "openai": threading.Lock(),
    "gemini": threading.Lock(),
    "azure_openai": threading.Lock(),
    "snowflake": threading.Lock(),
    "elasticsearch": threading.Lock()
}

async def get_embedding(
    text: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 30,
    query_params: Optional[dict] = None
) -> List[float]:
    """
    Get embedding for the provided text using the specified provider and model.

    Args:
        text: The text to embed
        provider: Optional provider name, defaults to preferred_embedding_provider
        model: Optional model name, defaults to the provider's configured model
        timeout: Maximum time to wait for embedding response in seconds
        query_params: Optional query parameters from HTTP request

    Returns:
        List of floats representing the embedding vector
    """
    config = get_config()

    # Allow overriding provider in development mode
    if config.is_development_mode() and query_params:
        if 'embedding_provider' in query_params:
            provider = query_params['embedding_provider']

    provider = provider or config.preferred_embedding_provider

    # Truncate text to 20k characters to avoid token limit issues
    MAX_CHARS = 20000
    original_length = len(text)
    if original_length > MAX_CHARS:
        text = text[:MAX_CHARS]


    if provider not in config.embedding_providers:
        error_msg = f"Unknown embedding provider '{provider}'"
        raise ValueError(error_msg)

    # Get provider config using the helper method
    provider_config = config.get_embedding_provider(provider)
    if not provider_config:
        error_msg = f"Missing configuration for embedding provider '{provider}'"
        raise ValueError(error_msg)

    # Use the provided model or fall back to the configured model
    model_id = model or provider_config.model
    if not model_id:
        error_msg = f"No embedding model specified for provider '{provider}'"
        raise ValueError(error_msg)


    try:
        # Use config-driven dynamic import
        if not provider_config.import_path or not provider_config.class_name:
            error_msg = f"No import_path and class_name configured for embedding provider '{provider}'"
            raise ValueError(error_msg)

        # Dynamic import based on config
        import_path = provider_config.import_path
        class_name = provider_config.class_name

        try:
            module = __import__(import_path, fromlist=[class_name])
            embedding_callable = getattr(module, class_name)

            # Call the embedding function with timeout
            result = await asyncio.wait_for(
                embedding_callable(text, model=model_id),
                timeout=timeout
            )
            return result
        except (ImportError, AttributeError) as e:
            error_msg = f"Failed to load embedding provider '{provider}': {e}"
            raise ValueError(error_msg)

    except asyncio.TimeoutError:
        raise
    except Exception as e:
        raise
