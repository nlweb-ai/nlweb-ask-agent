# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
LLM provider interface and orchestration.

This module provides:
1. GenerativeLLMProvider abstract base class for LLM providers that generate text/JSON
2. Orchestration functions for loading providers and routing requests

For scoring-only providers (e.g., Pi Labs), see nlweb_core.scoring.ScoringLLMProvider.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.

"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, TypeVar, Type
from nlweb_core.config import get_config
from nlweb_core.llm_exceptions import (
    LLMTimeoutError,
    LLMValidationError,
    classify_llm_error,
)
from pydantic import BaseModel, ValidationError
import asyncio
import logging

logger = logging.getLogger(__name__)

# TypeVar for Pydantic model return type inference
T = TypeVar("T", bound=BaseModel)


class GenerativeLLMProvider(ABC):
    """
    Abstract base class for generative LLM providers.

    This class defines the interface for LLM providers that generate text or
    structured JSON responses. Providers like Azure OpenAI implement this interface.

    For scoring-only providers (that always return numeric scores),
    see nlweb_core.scoring.ScoringLLMProvider instead.
    """

    @abstractmethod
    async def get_completion(
        self,
        prompt: str,
        schema: Dict[str, Any],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: float = 30.0,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Send a completion request to the LLM provider and return the parsed response.

        Args:
            prompt: The text prompt to send to the LLM
            schema: JSON schema that the response should conform to
            model: The specific model to use (if None, use default from config)
            temperature: Controls randomness of the output (0-1)
            max_tokens: Maximum tokens in the generated response
            timeout: Request timeout in seconds
            **kwargs: Additional provider-specific arguments

        Returns:
            Parsed JSON response from the LLM

        Raises:
            TimeoutError: If the request times out
            ValueError: If the response cannot be parsed or request fails
        """
        pass

    async def get_completions(
        self,
        prompts: list[str],
        schema: Dict[str, Any],
        query_kwargs_list: list[dict[str, Any]] | None = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: float = 30.0,
        **kwargs,
    ) -> list[dict[str, Any] | BaseException]:
        """Send multiple requests to the model in parallel and return parsed responses."""
        tasks = []
        for i, prompt in enumerate(prompts):
            query_kwargs = query_kwargs_list[i] if query_kwargs_list else {}
            tasks.append(
                self.get_completion(
                    prompt,
                    schema,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    **{**kwargs, **query_kwargs},
                )
            )
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

    @classmethod
    @abstractmethod
    def get_client(cls, **kwargs) -> Any:
        """
        Get or initialize the client for this provider.
        Returns a client instance ready to make API calls.

        Args:
            **kwargs: Provider-specific configuration (endpoint, api_key, etc.)

        Returns:
            A client instance configured for the provider
        """
        pass

    @classmethod
    @abstractmethod
    def clean_response(cls, content: str) -> Dict[str, Any]:
        """
        Clean and parse the raw response content into a structured dict.

        Args:
            content: Raw response content from the LLM

        Returns:
            Parsed JSON as a Python dictionary

        Raises:
            ValueError: If the content doesn't contain valid JSON
        """
        pass


# Cache for loaded providers
_loaded_providers = {}


def _get_provider(llm_type: str, provider_config=None):
    """
    Lazily load and return the provider for the given LLM type.

    Args:
        llm_type: The type of LLM provider to load
        provider_config: Optional provider config with import_path and class_name

    Returns:
        The provider instance

    Raises:
        ValueError: If the LLM type is unknown
    """
    # Return cached provider if already loaded
    if llm_type in _loaded_providers:
        return _loaded_providers[llm_type]

    # Use config-driven dynamic import if available
    if provider_config and provider_config.import_path and provider_config.class_name:
        try:
            import_path = provider_config.import_path
            class_name = provider_config.class_name
            module = __import__(import_path, fromlist=[class_name])
            provider_class = getattr(module, class_name)
            # Instantiate if it's a class, or use directly if it's already an instance
            provider = provider_class() if callable(provider_class) else provider_class
            _loaded_providers[llm_type] = provider
        except (ImportError, AttributeError) as e:
            raise ValueError(f"Failed to load provider for {llm_type}: {e}")
    else:
        raise ValueError(
            f"No import_path and class_name configured for LLM type: {llm_type}"
        )

    return _loaded_providers[llm_type]


async def ask_llm_parallel(
    prompts: list[str],
    schema: Type[T],
    provider: Optional[str] = None,
    level: str = "low",
    timeout: int = 8,
    query_params_list: list[dict[str, Any]] = [],
    max_length: int = 512,
) -> list[T | LLMValidationError | Exception]:
    """
    Route an LLM request to the specified endpoint, with dispatch based on llm_type.

    Args:
        prompts: The text prompts to send to the LLM
        schema: A Pydantic model class (Type[BaseModel]) for validated responses
        provider: The LLM endpoint to use (if None, use model config based on level)
        level: The model tier to use ('low', 'high', or 'scoring')
        timeout: Request timeout in seconds
        query_params_list: Optional query parameters for development mode provider override
        max_length: Maximum length of the response in tokens (default: 512)

    Returns:
        list[T | LLMValidationError | Exception]: List of validated model instances,
        or LLMValidationError for responses that fail validation,
        or Exception for other errors from the provider

    Raises:
        LLMTimeoutError: If the overall request times out
        LLMError: For other LLM-related errors
    """
    # Convert Pydantic model to JSON schema for LLM provider
    json_schema: Dict[str, Any] = schema.model_json_schema()
    # Get model config based on level (new format) or fall back to old format
    config = get_config()
    model_config = None
    model_id = None
    llm_type = None

    if level == "high" and config.high_llm_model:
        model_config = config.high_llm_model
        model_id = model_config.model
        llm_type = model_config.llm_type
    elif level == "low" and config.low_llm_model:
        model_config = config.low_llm_model
        model_id = model_config.model
        llm_type = model_config.llm_type
    elif level == "scoring" and config.scoring_llm_model:
        model_config = config.scoring_llm_model
        model_id = model_config.model
        llm_type = model_config.llm_type
    elif (
        config.preferred_llm_endpoint
        and config.preferred_llm_endpoint in config.llm_endpoints
    ):
        # Fall back to old format
        provider_name = provider or config.preferred_llm_endpoint
        provider_config = config.get_llm_provider(provider_name)
        if not provider_config or not provider_config.models:
            return []
        llm_type = provider_config.llm_type
        model_id = getattr(
            provider_config.models, level if level in ["high", "low"] else "low"
        )
        model_config = provider_config
    else:
        return []

    try:
        # Get the provider instance based on llm_type
        try:
            provider_instance = _get_provider(llm_type, model_config)
        except ValueError as e:
            return []

        logger.debug(
            f"Calling LLM provider {provider_instance} with model {model_id} at level {level}"
        )
        logger.debug(f"Model config: {model_config}")

        # Extract values from model config
        endpoint_val = (
            model_config.endpoint if hasattr(model_config, "endpoint") else None
        )
        api_version_val = (
            model_config.api_version if hasattr(model_config, "api_version") else None
        )
        api_key_val = model_config.api_key if hasattr(model_config, "api_key") else None

        # Simply call the provider's get_completion method, passing all config parameters
        # Each provider should handle thread-safety internally
        raw_results = await asyncio.wait_for(
            provider_instance.get_completions(
                prompts,
                json_schema,
                model=model_id,
                timeout=timeout,
                max_tokens=max_length,
                endpoint=endpoint_val,
                api_key=api_key_val,
                api_version=api_version_val,
                auth_method=(
                    model_config.auth_method
                    if hasattr(model_config, "auth_method")
                    else None
                ),
                kwargs_list=query_params_list,
            ),
            timeout=timeout,
        )

        # Validate and convert results to Pydantic models
        validated_results: list[T | LLMValidationError | Exception] = []
        for raw_result in raw_results:
            # Pass through exceptions unchanged
            if isinstance(raw_result, Exception):
                validated_results.append(raw_result)
                continue

            # Validate dict against Pydantic model
            try:
                validated_results.append(schema.model_validate(raw_result))
            except ValidationError as e:
                validated_results.append(
                    LLMValidationError(
                        f"LLM response failed validation: {e}",
                        raw_response=raw_result,
                        validation_error=e,
                    )
                )
        return validated_results

    except asyncio.TimeoutError as e:
        # Timeout is a specific, well-known error - raise it directly
        logger.error(f"LLM request timed out after {timeout}s", exc_info=True)
        raise LLMTimeoutError(f"LLM request timed out after {timeout}s") from e

    except Exception as e:
        # Classify the error and raise appropriate exception
        logger.error(f"LLM request failed: {e}", exc_info=True)
        classified_error = classify_llm_error(e)
        raise classified_error from e


async def ask_llm(
    prompt: str,
    schema: Dict[str, Any],
    provider: Optional[str] = None,
    level: str = "low",
    timeout: int = 8,
    query_params: Optional[Dict[str, Any]] = None,
    max_length: int = 512,
) -> Dict[str, Any]:
    """
    Route an LLM request to the specified endpoint, with dispatch based on llm_type.

    Args:
        prompt: The text prompt to send to the LLM
        schema: JSON schema that the response should conform to
        provider: The LLM endpoint to use (if None, use model config based on level)
        level: The model tier to use ('low', 'high', or 'scoring')
        timeout: Request timeout in seconds
        query_params: Optional query parameters for development mode provider override
        max_length: Maximum length of the response in tokens (default: 512)

    Returns:
        Parsed JSON response from the LLM

    Raises:
        ValueError: If the endpoint is unknown or response cannot be parsed
        TimeoutError: If the request times out
    """
    # Get model config based on level (new format) or fall back to old format
    config = get_config()
    model_config = None
    model_id = None
    llm_type = None

    if level == "high" and config.high_llm_model:
        model_config = config.high_llm_model
        model_id = model_config.model
        llm_type = model_config.llm_type
    elif level == "low" and config.low_llm_model:
        model_config = config.low_llm_model
        model_id = model_config.model
        llm_type = model_config.llm_type
    elif level == "scoring" and config.scoring_llm_model:
        model_config = config.scoring_llm_model
        model_id = model_config.model
        llm_type = model_config.llm_type
    elif (
        config.preferred_llm_endpoint
        and config.preferred_llm_endpoint in config.llm_endpoints
    ):
        # Fall back to old format
        provider_name = provider or config.preferred_llm_endpoint
        provider_config = config.get_llm_provider(provider_name)
        if not provider_config or not provider_config.models:
            return {}
        llm_type = provider_config.llm_type
        model_id = getattr(
            provider_config.models, level if level in ["high", "low"] else "low"
        )
        model_config = provider_config
    else:
        return {}

    try:
        # Get the provider instance based on llm_type
        try:
            provider_instance = _get_provider(llm_type, model_config)
        except ValueError as e:
            return {}

        logger.debug(
            f"Calling LLM provider {provider_instance} with model {model_id} at level {level}"
        )
        logger.debug(f"Model config: {model_config}")

        # Extract values from model config
        endpoint_val = (
            model_config.endpoint if hasattr(model_config, "endpoint") else None
        )
        api_version_val = (
            model_config.api_version if hasattr(model_config, "api_version") else None
        )
        api_key_val = model_config.api_key if hasattr(model_config, "api_key") else None

        # Simply call the provider's get_completion method, passing all config parameters
        # Each provider should handle thread-safety internally
        result = await asyncio.wait_for(
            provider_instance.get_completion(
                prompt,
                schema,
                model=model_id,
                timeout=timeout,
                max_tokens=max_length,
                endpoint=endpoint_val,
                api_key=api_key_val,
                api_version=api_version_val,
                auth_method=(
                    model_config.auth_method
                    if hasattr(model_config, "auth_method")
                    else None
                ),
                **(query_params or {}),
            ),
            timeout=timeout,
        )
        return result

    except asyncio.TimeoutError as e:
        # Timeout is a specific, well-known error - raise it directly
        logger.error(f"LLM request timed out after {timeout}s", exc_info=True)
        raise LLMTimeoutError(f"LLM request timed out after {timeout}s") from e

    except Exception as e:
        # Classify the error and raise appropriate exception
        logger.error(f"LLM request failed: {e}", exc_info=True)
        classified_error = classify_llm_error(e)
        raise classified_error from e


def get_available_providers() -> list:
    """
    Get a list of LLM providers that have their required API keys available.

    Returns:
        List of provider names that are available for use.
    """
    available_providers = []
    config = get_config()

    for provider_name, provider_config in config.llm_endpoints.items():
        # Check if provider config exists and has required fields
        if (
            provider_config
            and hasattr(provider_config, "api_key")
            and provider_config.api_key
            and provider_config.api_key.strip() != ""
            and hasattr(provider_config, "models")
            and provider_config.models
            and provider_config.models.high
            and provider_config.models.low
        ):
            available_providers.append(provider_name)

    return available_providers
