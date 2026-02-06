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

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from nlweb_core.config import get_config
from nlweb_core.llm_exceptions import (
    LLMTimeoutError,
    LLMValidationError,
    classify_llm_error,
)

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
    def __init__(self, **kwargs) -> None:
        """
        Initialize the provider with configuration.

        Args:
            **kwargs: Provider-specific configuration (model, endpoint, api_key, etc.)
        """
        pass

    @abstractmethod
    async def get_completion(
        self,
        prompt: str,
        schema: Dict[str, Any],
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
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    **{**kwargs, **query_kwargs},
                )
            )
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return list(results)

    @abstractmethod
    async def close(self) -> None:
        """Close the provider and release resources."""
        pass


async def ask_llm_parallel(
    prompts: list[str],
    schema: Type[T],
    level: str = "low",
    timeout: int = 8,
    query_params_list: list[dict[str, Any]] = [],
    max_length: int = 512,
) -> list[T | LLMValidationError | BaseException]:
    """
    Route an LLM request to the configured generative provider.

    Args:
        prompts: The text prompts to send to the LLM
        schema: A Pydantic model class (Type[BaseModel]) for validated responses
        level: The model tier to use ('low', 'high', or 'scoring')
        timeout: Request timeout in seconds
        query_params_list: Optional query parameters for development mode provider override
        max_length: Maximum length of the response in tokens (default: 512)

    Returns:
        list[T | LLMValidationError | BaseException]: List of validated model instances,
        or LLMValidationError for responses that fail validation,
        or BaseException for other errors from the provider

    Raises:
        LLMTimeoutError: If the overall request times out
        LLMError: For other LLM-related errors
    """
    # Convert Pydantic model to JSON schema for LLM provider
    json_schema: Dict[str, Any] = schema.model_json_schema()

    try:
        # Get the provider instance via factory
        try:
            provider_instance = get_config().get_generative_provider(level)
        except ValueError:
            logger.warning(f"No generative provider configured for level '{level}'")
            return []

        logger.debug(f"Calling LLM provider {provider_instance} at level {level}")

        from nlweb_core.metrics import ASK_LLM_CALL_DURATION

        llm_start = time.monotonic()
        raw_results = await asyncio.wait_for(
            provider_instance.get_completions(
                prompts,
                json_schema,
                timeout=timeout,
                max_tokens=max_length,
                kwargs_list=query_params_list,
            ),
            timeout=timeout,
        )
        ASK_LLM_CALL_DURATION.labels(operation=level).observe(
            time.monotonic() - llm_start
        )

        # Validate and convert results to Pydantic models
        validated_results: list[T | LLMValidationError | BaseException] = []
        for raw_result in raw_results:
            # Pass through exceptions unchanged
            if isinstance(raw_result, BaseException):
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
    schema: Type[T],
    level: str = "low",
    timeout: int = 8,
    query_params: Optional[Dict[str, Any]] = None,
    max_length: int = 512,
) -> T:
    """
    Route an LLM request to the configured generative provider.

    Args:
        prompt: The text prompt to send to the LLM
        schema: A Pydantic model class for type-safe responses
        level: The model tier to use ('low', 'high', or 'scoring')
        timeout: Request timeout in seconds
        query_params: Optional query parameters for development mode provider override
        max_length: Maximum length of the response in tokens (default: 512)

    Returns:
        Validated Pydantic model instance

    Raises:
        ValueError: If the endpoint is unknown or response cannot be parsed
        TimeoutError: If the request times out
        LLMValidationError: If the response fails Pydantic validation
    """
    # Convert Pydantic model to JSON schema for the provider
    json_schema: Dict[str, Any] = schema.model_json_schema()

    try:
        # Get the provider instance via factory
        provider_instance = get_config().get_generative_provider(level)

        logger.debug(f"Calling LLM provider {provider_instance} at level {level}")

        from nlweb_core.metrics import ASK_LLM_CALL_DURATION

        # Call the provider's get_completion method
        # Provider has model config from __init__
        llm_start = time.monotonic()
        raw_result = await asyncio.wait_for(
            provider_instance.get_completion(
                prompt,
                json_schema,
                timeout=timeout,
                max_tokens=max_length,
                **(query_params or {}),
            ),
            timeout=timeout,
        )
        ASK_LLM_CALL_DURATION.labels(operation=level).observe(
            time.monotonic() - llm_start
        )

        # Validate and return Pydantic model instance
        try:
            return schema.model_validate(raw_result)
        except ValidationError as e:
            raise LLMValidationError(
                f"LLM response failed validation: {e}",
                raw_response=raw_result,
                validation_error=e,
            )

    except asyncio.TimeoutError as e:
        # Timeout is a specific, well-known error - raise it directly
        logger.error(f"LLM request timed out after {timeout}s", exc_info=True)
        raise LLMTimeoutError(f"LLM request timed out after {timeout}s") from e

    except Exception as e:
        # Classify the error and raise appropriate exception
        logger.error(f"LLM request failed: {e}", exc_info=True)
        classified_error = classify_llm_error(e)
        raise classified_error from e
