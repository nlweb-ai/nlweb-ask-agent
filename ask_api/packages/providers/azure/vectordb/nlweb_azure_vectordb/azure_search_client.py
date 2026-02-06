# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License


"""
Azure AI Search Client - Interface for Azure AI Search operations.
"""

import logging
import time
from typing import List, Dict, Union, Optional, Any

from azure.core.credentials import AzureKeyCredential
from azure.identity.aio import DefaultAzureCredential
from azure.search.documents.aio import SearchClient

# Type alias for credentials
CredentialType = Union[DefaultAzureCredential, AzureKeyCredential]

from nlweb_core.config import get_config
from nlweb_core.retriever import RetrievalProvider
from nlweb_core.retrieved_item import RetrievedItem
from nlweb_core.azure_credentials import get_azure_credential


logger = logging.getLogger(__name__)


class AzureSearchClient(RetrievalProvider):
    """
    Client for Azure AI Search operations, providing a unified interface for
    retrieving vector-based search results.
    """

    def __init__(
        self,
        api_endpoint: str,
        auth_method: str,
        index_name: str,
        api_key: str | None = None,
        **kwargs,
    ):
        """
        Initialize the Azure Search client.

        Args:
            api_endpoint: Azure Search endpoint URL.
            auth_method: Authentication method ('api_key' or 'azure_ad').
            api_key: API key (required when auth_method is 'api_key').
            index_name: Default search index name.
            **kwargs: Additional provider-specific configuration.
        """
        self.auth_method = auth_method
        self.api_endpoint = api_endpoint.strip('"')
        self.default_index_name = index_name

        # API key is only required for api_key authentication
        if self.auth_method == "api_key":
            if not api_key:
                raise ValueError("api_key is required for api_key authentication")
            self.api_key = api_key.strip('"')
        elif self.auth_method == "azure_ad":
            # No API key needed for managed identity
            self.api_key = None
        else:
            raise ValueError(
                f"Unsupported authentication method: {self.auth_method}. Use 'api_key' or 'azure_ad'"
            )

        # Clients initialized lazily on first use, cached per index
        self._clients: Dict[str, SearchClient] = {}
        self._credential: Optional[CredentialType] = None

    async def _ensure_credential(self) -> CredentialType:
        """Create credential if not already initialized."""
        if self.auth_method == "azure_ad":
            return await get_azure_credential()
        elif self.auth_method == "api_key":
            assert self.api_key is not None  # Validated in __init__
            return AzureKeyCredential(self.api_key)
        else:
            raise ValueError(f"Unsupported authentication method: {self.auth_method}")

    async def _ensure_client(self, index_name: Optional[str] = None) -> SearchClient:
        """
        Get or create client for the specified index.

        Args:
            index_name: Name of the index (defaults to the configured index name)

        Returns:
            SearchClient: The Azure Search client for the specified index
        """
        index_name = index_name or self.default_index_name

        if index_name not in self._clients:
            credential = await self._ensure_credential()
            self._clients[index_name] = SearchClient(
                endpoint=self.api_endpoint,
                index_name=index_name,
                credential=credential,
            )

        return self._clients[index_name]

    async def search(
        self,
        query: str,
        site: Union[str, List[str]],
        num_results: int = 50,
        index_name: Optional[str] = None,
        query_params: Optional[Dict[str, Any]] = None,
        date_filter: Optional[str] = None,
        **kwargs,
    ) -> List[RetrievedItem]:
        """
        Search the Azure AI Search index for records filtered by site and ranked by vector similarity

        Args:
            query: The search query to embed and search with
            site: Site to filter by (string or list of strings)
            num_results: Maximum number of results to return
            index_name: Optional index name (defaults to configured index name)
            query_params: Additional query parameters
            date_filter: Optional date filter (e.g., "datePublished ge 2026-02-01T00:00:00Z")

        Returns:
            List[RetrievedItem]: List of search results
        """
        index_name = index_name or self.default_index_name

        # Get embedding for the query
        start_embed = time.time()
        embedding_provider = get_config().get_embedding_provider("default")
        embedding = await embedding_provider.get_embedding(query)
        embed_time = time.time() - start_embed

        # Perform the search
        start_retrieve = time.time()
        results = await self._retrieve_by_site_and_vector(
            site, embedding, num_results, index_name, query_text=query, date_filter=date_filter
        )
        retrieve_time = time.time() - start_retrieve

        return results

    async def _retrieve_by_site_and_vector(
        self,
        sites: Union[str, List[str]],
        vector_embedding: List[float],
        top_n: int = 10,
        index_name: Optional[str] = None,
        query_text: Optional[str] = None,
        date_filter: Optional[str] = None,
    ) -> List[RetrievedItem]:
        """
        Internal method to retrieve top n records filtered by site and ranked by hybrid search (BM25 + vector)

        Args:
            sites: Site or list of sites to filter by
            vector_embedding: The embedding vector to search with
            top_n: Maximum number of results to return
            index_name: Optional index name (defaults to configured index name)
            query_text: Optional query text for hybrid search (BM25 + vector)
            date_filter: Optional date filter (e.g., "datePublished ge 2026-02-01T00:00:00Z")

        Returns:
            List[RetrievedItem]: List of search results
        """
        index_name = index_name or self.default_index_name

        # Validate embedding dimension
        if len(vector_embedding) != 1536:
            error_msg = f"Embedding dimension {len(vector_embedding)} not supported. Must be 1536."
            raise ValueError(error_msg)

        search_client = await self._ensure_client(index_name)

        # Handle both single site and multiple sites
        if isinstance(sites, str):
            sites = [sites]

        # Build site filter - skip if "all"
        site_restrict = None
        if sites != ["all"] and "all" not in sites:
            site_restrict = ""
            for site in sites:
                if len(site_restrict) > 0:
                    site_restrict += " or "
                site_restrict += f"site eq '{site}'"

        # Combine site filter and date filter
        combined_filter = None
        if site_restrict and date_filter:
            combined_filter = f"({site_restrict}) and ({date_filter})"
        elif site_restrict:
            combined_filter = site_restrict
        elif date_filter:
            combined_filter = date_filter

        # Create the search options with hybrid search (BM25 + vector)
        search_options = {
            "vector_queries": [
                {
                    "kind": "vector",
                    "vector": vector_embedding,
                    "fields": "embedding",
                    "k": top_n,
                }
            ],
            "top": top_n,
            "select": "url,type,site,content",
        }

        # Configure search mode for BM25
        if query_text:
            # Use "any" mode so BM25 doesn't filter too aggressively (OR logic)
            # This is more lenient than "all" mode (AND logic)
            search_options["search_mode"] = "any"
            logger.debug(f"Hybrid search (BM25 + vector, mode=any) for query: {query_text[:50]}...")
        else:
            logger.debug("Pure vector search (no query text)")

        # Add combined filter if we have any restrictions
        if combined_filter:
            search_options["filter"] = combined_filter
            if date_filter:
                logger.debug(f"Date filter applied: {date_filter}")

        try:
            # Execute the search - hybrid mode (BM25 + vector) if query_text provided
            # If no query_text, falls back to pure vector search
            results = await search_client.search(search_text=query_text, **search_options)

            # Process results into RetrievedItem objects (async iteration)
            processed_results = []
            async for result in results:
                try:
                    processed_result = RetrievedItem(
                        url=result["url"],
                        raw_schema_object=result["content"],
                        site=result["site"],
                    )
                    processed_results.append(processed_result)
                except Exception as e:
                    logger.error(f"Error processing result {result}: {e}")
                    raise

            return processed_results

        except Exception as e:
            logger.error(f"Error during Azure Search operation: {e}")
            raise e

    async def close(self):
        """Close all search clients and release resources."""
        for client in self._clients.values():
            await client.close()
        self._clients.clear()
