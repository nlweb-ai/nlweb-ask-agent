# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Embedding provider interface.

Defines the EmbeddingProvider abstract base class that all embedding
implementations must inherit from.
"""

from abc import ABC, abstractmethod
from typing import List
import asyncio
import logging


logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    """
    Abstract base class for embedding providers.

    Concrete implementations (e.g., AzureOpenAIEmbeddingProvider) implement
    the get_embedding and close methods. An optional batch method is provided
    with a default implementation that calls get_embedding in parallel.
    """

    @abstractmethod
    def __init__(self, **kwargs) -> None:
        """
        Initialize the provider with configuration.

        Args:
            **kwargs: Provider-specific configuration (endpoint, api_key, model, etc.)
        """
        pass

    @abstractmethod
    async def get_embedding(self, text: str, timeout: float = 30.0) -> List[float]:
        """
        Get embedding vector for a single text.

        Args:
            text: The text to embed
            timeout: Maximum time in seconds

        Returns:
            List of floats representing the embedding vector
        """
        pass

    async def get_batch_embeddings(
        self, texts: List[str], timeout: float = 60.0
    ) -> List[List[float]]:
        """
        Get embedding vectors for multiple texts.

        Default implementation calls get_embedding in parallel using gather.
        Concrete providers can override for native batch API support.

        Args:
            texts: List of texts to embed
            timeout: Maximum time in seconds

        Returns:
            List of embedding vectors
        """
        tasks = [self.get_embedding(text, timeout=timeout) for text in texts]
        return list(await asyncio.gather(*tasks))

    @abstractmethod
    async def close(self) -> None:
        """Close the provider and release resources."""
        pass
