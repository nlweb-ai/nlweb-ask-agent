# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
This file contains the VectorDB retriever implementation.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

from nlweb_core.config import get_config
from nlweb_core.item_retriever import ItemRetriever, RetrievedItem, RetrievalParams
from nlweb_core.retriever import (
    get_vectordb_client,
    enrich_results_from_object_storage,
)


class VectorDBRetriever(ItemRetriever):
    """Retriever that uses vector database search."""

    async def retrieve(self, params: RetrievalParams) -> list[RetrievedItem]:
        """
        Perform vector database search and return results.

        Args:
            params: RetrievalParams with query_text, site, num_results.

        Returns:
            List of RetrievedItem objects.
        """
        # Get the vector DB client and perform search
        vectordb_client = await get_vectordb_client()
        results = await vectordb_client.search(
            params.query_text, params.site, params.num_results
        )

        # Enrich with full content from object storage if configured
        config = get_config()
        if config.object_storage_providers:
            object_lookup_client = config.get_object_lookup_provider("default")
            results = await enrich_results_from_object_storage(
                results, object_lookup_client
            )

        return results
