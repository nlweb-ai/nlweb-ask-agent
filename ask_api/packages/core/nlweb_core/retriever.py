# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Retrieval and object lookup provider interfaces.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
from nlweb_core.item_retriever import ItemRetriever, RetrievedItem


class RetrievalProvider(ABC):
    """
    Abstract base class for retrieval providers (e.g., vector database clients).
    All retrieval implementations should implement the search method.
    """

    @abstractmethod
    def __init__(self, **kwargs) -> None:
        """
        Initialize the provider with configuration.

        Args:
            **kwargs: Provider-specific configuration (api_endpoint, api_key, etc.)
        """
        pass

    @abstractmethod
    async def search(
        self, query: str, site: Union[str, List[str]], num_results: int = 50, **kwargs
    ) -> List[RetrievedItem]:
        """
        Search for documents matching the query and site.

        Args:
            query: Search query string
            site: Site identifier or list of sites
            num_results: Maximum number of results to return
            **kwargs: Additional parameters

        Returns:
            List of RetrievedItem objects
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the client and release resources."""
        pass


class ObjectLookupProvider(ABC):
    """
    Abstract base class for looking up full objects by their ID.
    Implementations should fetch complete object data from storage (e.g., Cosmos DB).
    """

    @abstractmethod
    def __init__(self, **kwargs) -> None:
        """
        Initialize the provider with configuration.

        Args:
            **kwargs: Provider-specific configuration (endpoint, database_name, etc.)
        """
        pass

    @abstractmethod
    async def get_by_id(self, object_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a complete object by its ID.

        Args:
            object_id: The unique identifier for the object (e.g., URL/@id)

        Returns:
            Complete object as dictionary, or None if not found
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the client and release resources."""
        pass


async def enrich_results_from_object_storage(
    results: List[RetrievedItem],
    client: ObjectLookupProvider,
) -> List[RetrievedItem]:
    """
    Enrich vector DB results with full content from object storage.
    Replaces the potentially empty content with complete object data from Cosmos DB.

    Args:
        results: List of RetrievedItem objects from vector DB search
        client: Object lookup client to fetch full objects

    Returns:
        Enriched RetrievedItem list with full content from object storage
    """
    # Control Concurrency: Allow max 20 parallel requests at a time
    # Adjust this based on the RU capacity. 20-50 is usually safe for standard workloads.
    semaphore = asyncio.Semaphore(20)

    async def process_single_result(result: RetrievedItem) -> RetrievedItem:
        """
        Helper function to process one item.
        """
        async with semaphore:
            full_object = await client.get_by_id(result.url)

        if full_object:
            # Replace content with full object dict
            return RetrievedItem(
                url=result.url,
                raw_schema_object=full_object,
                site=result.site,
            )
        else:
            # Keep original if not found
            return result

    tasks = [process_single_result(r) for r in results]

    enriched_results = await asyncio.gather(*tasks)

    return list(enriched_results)


def get_item_retriever() -> ItemRetriever:
    """
    Factory function to get the configured ItemRetriever instance.

    Returns:
        ItemRetriever instance (currently VectorDBRetriever)
    """
    from nlweb_core.vector_db_retriever import VectorDBRetriever

    return VectorDBRetriever()
