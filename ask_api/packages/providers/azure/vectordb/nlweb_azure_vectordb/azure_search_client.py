# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License


"""
Azure AI Search Client - Interface for Azure AI Search operations.
"""

import logging
import sys
import time
import threading
import asyncio
from typing import List, Dict, Union, Optional, Any, Tuple

from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient

from nlweb_core.embedding import get_embedding
from nlweb_core.retriever import VectorDBClientInterface
from nlweb_core.item_retriever import RetrievedItem


logger = logging.getLogger(__name__)


class AzureSearchClient(VectorDBClientInterface):
    """
    Client for Azure AI Search operations, providing a unified interface for
    retrieving vector-based search results.
    """

    def __init__(self, endpoint_config):
        """
        Initialize the Azure Search client.

        Args:
            endpoint_config: Endpoint configuration object with api_endpoint, api_key, index_name, etc.
        """
        super().__init__()
        self.endpoint_config = endpoint_config
        self._client_lock = threading.Lock()
        self._search_clients = {}  # Cache for search clients

        # Get authentication method
        self.auth_method = (
            endpoint_config.auth_method
            if hasattr(endpoint_config, "auth_method") and endpoint_config.auth_method
            else "api_key"
        )

        # Safely handle None values for endpoint
        if (
            not hasattr(endpoint_config, "api_endpoint")
            or endpoint_config.api_endpoint is None
        ):
            raise ValueError(f"api_endpoint is not configured")

        self.api_endpoint = endpoint_config.api_endpoint.strip('"')
        self.default_index_name = (
            endpoint_config.index_name
            if hasattr(endpoint_config, "index_name") and endpoint_config.index_name
            else "crawler-vectors"
        )

        # API key is only required for api_key authentication
        if self.auth_method == "api_key":
            if (
                not hasattr(endpoint_config, "api_key")
                or endpoint_config.api_key is None
            ):
                raise ValueError(f"api_key is not configured")
            self.api_key = endpoint_config.api_key.strip('"')
        elif self.auth_method == "azure_ad":
            # No API key needed for managed identity
            self.api_key = None
        else:
            raise ValueError(
                f"Unsupported authentication method: {self.auth_method}. Use 'api_key' or 'azure_ad'"
            )

    def _get_search_client(self, index_name: Optional[str] = None) -> SearchClient:
        """
        Get the Azure AI Search client for a specific index

        Args:
            index_name: Name of the index (defaults to the configured index name)

        Returns:
            SearchClient: The Azure Search client for the specified index
        """
        index_name = index_name or self.default_index_name

        with self._client_lock:
            if index_name not in self._search_clients:
                # Create credential based on authentication method
                if self.auth_method == "azure_ad":
                    credential = DefaultAzureCredential()
                elif self.auth_method == "api_key":
                    credential = AzureKeyCredential(self.api_key)
                else:
                    raise ValueError(
                        f"Unsupported authentication method: {self.auth_method}"
                    )

                self._search_clients[index_name] = SearchClient(
                    endpoint=self.api_endpoint,
                    index_name=index_name,
                    credential=credential,
                )

        return self._search_clients[index_name]

    async def search(
        self,
        query: str,
        site: Union[str, List[str]],
        num_results: int = 50,
        index_name: Optional[str] = None,
        query_params: Optional[Dict[str, Any]] = None,
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

        Returns:
            List[RetrievedItem]: List of search results
        """
        index_name = index_name or self.default_index_name

        # Get embedding for the query
        start_embed = time.time()
        embedding = await get_embedding(query, query_params=query_params)
        embed_time = time.time() - start_embed

        # Perform the search
        start_retrieve = time.time()
        results = await self._retrieve_by_site_and_vector(
            site, embedding, num_results, index_name
        )
        retrieve_time = time.time() - start_retrieve

        return results

    async def _retrieve_by_site_and_vector(
        self,
        sites: Union[str, List[str]],
        vector_embedding: List[float],
        top_n: int = 10,
        index_name: Optional[str] = None,
    ) -> List[RetrievedItem]:
        """
        Internal method to retrieve top n records filtered by site and ranked by vector similarity

        Args:
            sites: Site or list of sites to filter by
            vector_embedding: The embedding vector to search with
            top_n: Maximum number of results to return
            index_name: Optional index name (defaults to configured index name)

        Returns:
            List[RetrievedItem]: List of search results
        """
        index_name = index_name or self.default_index_name

        # Validate embedding dimension
        if len(vector_embedding) != 1536:
            error_msg = f"Embedding dimension {len(vector_embedding)} not supported. Must be 1536."
            raise ValueError(error_msg)

        search_client = self._get_search_client(index_name)

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

        # Create the search options with vector search and filtering
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

        # Only add filter if we have a site restriction
        if site_restrict:
            search_options["filter"] = site_restrict

        try:
            # Execute the search asynchronously
            def search_sync():
                return search_client.search(search_text=None, **search_options)

            results = await asyncio.get_event_loop().run_in_executor(None, search_sync)

            # Process results into RetrievedItem objects
            processed_results = []
            for result in results:
                try:
                    processed_result = RetrievedItem(
                        url=result["url"],
                        raw_schema_object=result["content"],
                        site=result["site"],
                    )
                except Exception as e:
                    logger.error(f"Error processing result {result}: {e}")
                    print(f"Error processing result {result}: {e}", file=sys.stderr)
                    continue
                processed_results.append(processed_result)

            return processed_results

        except Exception as e:
            import traceback

            traceback.print_exc()
            return []
