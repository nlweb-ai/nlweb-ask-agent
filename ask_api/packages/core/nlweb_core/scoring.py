# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Scoring provider interface and orchestration.

This module provides:
1. ScoringLLMProvider abstract base class for providers that return numeric scores
2. ScoringContext dataclass for passing structured context to scoring operations
3. get_scoring_provider() factory function for loading configured scoring providers

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import asyncio
import logging

from nlweb_core.config import get_config
from nlweb_core.provider_map import ProviderMap

logger = logging.getLogger(__name__)


@dataclass
class ScoringContext:
    """Context for scoring operations.

    This provides structured context for different scoring use cases:
    - Item ranking: query + item_description + item_type + publication_date + age_days
    - Intent detection: query + intent
    - Presence checking: query + required_info
    """

    query: str
    """The user's query text."""

    item_description: str | None = None
    """For item ranking: JSON string of the item's schema object."""

    item_type: str | None = None
    """For item ranking: the type of item being ranked (e.g., 'Recipe', 'Restaurant')."""

    intent: str | None = None
    """For intent detection: the intent being checked."""

    required_info: str | None = None
    """For presence checking: the required information being checked."""

    publication_date: str | None = None
    """For freshness-aware ranking: ISO format publication date string."""

    age_days: int | None = None
    """For freshness-aware ranking: Days since publication (calculated from datePublished)."""


class ScoringLLMProvider(ABC):
    """
    Abstract base class for scoring providers that return numeric scores.

    Unlike GenerativeLLMProvider which generates text/JSON responses,
    scoring providers always return a numeric score (0-100).

    This interface is designed for:
    - Item ranking (relevance scoring)
    - Intent detection
    - Presence checking
    """

    @abstractmethod
    def __init__(self, **kwargs) -> None:
        """
        Initialize the provider with configuration.

        Args:
            **kwargs: Provider-specific configuration (endpoint, api_key, etc.)
        """
        pass

    @abstractmethod
    async def score(
        self,
        questions: list[str],
        context: ScoringContext,
        timeout: float = 30.0,
        **kwargs,
    ) -> float:
        """
        Score a single context with the given questions.

        Args:
            questions: List of scoring questions (e.g., ["Is this item relevant to the query?"])
            context: Structured context for the scoring operation
            timeout: Request timeout in seconds
            **kwargs: Additional provider-specific arguments (api_key, endpoint, etc.)

        Returns:
            Score between 0-100

        Raises:
            TimeoutError: If the request times out
            ValueError: If the request fails
        """
        pass

    async def score_batch(
        self,
        questions: list[str],
        contexts: list[ScoringContext],
        timeout: float = 30.0,
        **kwargs,
    ) -> list[float | BaseException]:
        """
        Score multiple contexts with the given questions in parallel.

        Default implementation calls score() for each context using the first question.
        Providers can override this for optimized batch processing with multiple questions.

        Args:
            questions: List of scoring questions to ask
            contexts: List of contexts to score
            timeout: Request timeout in seconds
            **kwargs: Additional provider-specific arguments

        Returns:
            List of scores (0-100) or Exception for each failed request
        """
        tasks = [
            self.score(questions, context, timeout=timeout, **kwargs)
            for context in contexts
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return list(results)

    @abstractmethod
    async def close(self) -> None:
        """Close the provider and release resources."""
        pass


# Provider map for scoring LLM providers
_scoring_provider_map: ProviderMap[ScoringLLMProvider] = ProviderMap(
    config_getter=lambda name: get_config().get_scoring_model_provider(name),
    error_prefix="Scoring model provider",
)


def get_scoring_provider(name: str) -> ScoringLLMProvider:
    """
    Get the configured scoring provider by name via dynamic import.

    Uses get_config().get_scoring_model_provider(name) to load the appropriate provider.

    Args:
        name: Provider name

    Returns:
        The configured ScoringLLMProvider instance

    Raises:
        ValueError: If no scoring provider with the given name is configured
    """
    return _scoring_provider_map.get(name)
