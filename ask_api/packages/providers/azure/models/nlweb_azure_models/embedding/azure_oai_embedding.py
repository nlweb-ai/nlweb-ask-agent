# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Azure OpenAI embedding provider implementation.
"""

import logging
from typing import List
from openai import AsyncAzureOpenAI
from nlweb_core.embedding import EmbeddingProvider
from nlweb_core.azure_credentials import get_openai_token_provider


logger = logging.getLogger(__name__)

MAX_SINGLE_CHARS = 20000
MAX_BATCH_CHARS = 12000


class AzureOpenAIEmbeddingProvider(EmbeddingProvider):
    """Embedding provider using Azure OpenAI."""

    def __init__(
        self,
        endpoint: str,
        auth_method: str,
        model: str,
        api_version: str,
        api_key: str | None = None,
        **kwargs,
    ):
        self.endpoint = endpoint
        self.api_key = api_key
        self.auth_method = auth_method
        self.model = model
        self.api_version = api_version
        self._client: AsyncAzureOpenAI | None = None

    async def _ensure_client(self) -> None:
        """Create client if not already initialized."""
        if self._client is not None:
            return

        if self.auth_method == "azure_ad":
            token_provider = await get_openai_token_provider()
            self._client = AsyncAzureOpenAI(
                azure_endpoint=self.endpoint,
                azure_ad_token_provider=token_provider,
                api_version=self.api_version,
                timeout=30.0,
            )
        elif self.auth_method == "api_key":
            self._client = AsyncAzureOpenAI(
                azure_endpoint=self.endpoint,
                api_key=self.api_key,
                api_version=self.api_version,
                timeout=30.0,
            )
        else:
            raise ValueError(f"Unsupported authentication method: {self.auth_method}")

    async def get_embedding(self, text: str, timeout: float = 30.0) -> List[float]:
        """Get embedding for text using Azure OpenAI."""
        await self._ensure_client()
        assert self._client is not None

        if len(text) > MAX_SINGLE_CHARS:
            text = text[:MAX_SINGLE_CHARS]

        response = await self._client.embeddings.create(
            input=text, model=self.model
        )
        return response.data[0].embedding

    async def get_batch_embeddings(
        self, texts: List[str], timeout: float = 60.0
    ) -> List[List[float]]:
        """Get embeddings for multiple texts using Azure OpenAI native batch API."""
        await self._ensure_client()
        assert self._client is not None

        trimmed = [t[:MAX_BATCH_CHARS] if len(t) > MAX_BATCH_CHARS else t for t in texts]

        response = await self._client.embeddings.create(
            input=trimmed, model=self.model
        )
        return [data.embedding for data in response.data]

    async def close(self) -> None:
        """Close the Azure OpenAI client."""
        if self._client is not None:
            await self._client.close()
            self._client = None
