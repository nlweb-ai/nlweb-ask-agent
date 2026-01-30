# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Unified vector database interface with support for Azure AI Search, Milvus, and Qdrant.
This module provides abstract base classes and concrete implementations for database operations.
"""

import asyncio
import importlib
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
from collections import defaultdict
from nlweb_core.config import get_config, RetrievalProviderConfig
from nlweb_core.item_retriever import ItemRetriever, RetrievedItem

# Client cache for reusing instances
_client_cache = {}
_client_cache_locks = defaultdict(asyncio.Lock)  # Per-key locks instead of global lock

# Preloaded client modules
_preloaded_modules = {}

# Object lookup client cache
_object_lookup_client: Optional["ObjectLookupInterface"] = None
_object_lookup_lock = asyncio.Lock()


class VectorDBClientInterface(ABC):
    """
    Abstract base class defining the interface for vector database clients.
    All vector database implementations should implement the search method.
    """

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


class ObjectLookupInterface(ABC):
    """
    Abstract base class for looking up full objects by their ID.
    Implementations should fetch complete object data from storage (e.g., Cosmos DB).
    """

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


async def get_object_lookup_client() -> Optional[ObjectLookupInterface]:
    """
    Get or create the object lookup client based on configuration.
    Uses dynamic loading via import_path and class_name.

    Returns:
        ObjectLookupInterface instance or None if not configured
    """
    global _object_lookup_client

    config = get_config()

    # Check if object storage is enabled
    if not config.object_storage or not config.object_storage.enabled:
        return None

    # If client is already created, return immediately.
    if _object_lookup_client is not None:
        return _object_lookup_client

    async with _object_lookup_lock:
        if _object_lookup_client is None:
            # Use dynamic import based on config
            if (
                not config.object_storage.import_path
                or not config.object_storage.class_name
            ):
                raise ValueError(
                    f"Object storage config missing import_path or class_name for type: {config.object_storage.type}"
                )

            try:
                import_path = config.object_storage.import_path
                class_name = config.object_storage.class_name
                module = importlib.import_module(import_path)
                client_class = getattr(module, class_name)
                _object_lookup_client = client_class()
            except ImportError as e:
                raise ValueError(f"Failed to load object storage client: {e}")

        return _object_lookup_client


async def close_object_lookup_client():
    """
    Close the object lookup client and release resources.
    Should be called during application shutdown.
    """
    global _object_lookup_client

    async with _object_lookup_lock:
        if _object_lookup_client is not None:
            await _object_lookup_client.close()
            _object_lookup_client = None


async def enrich_results_from_object_storage(
    results: List[RetrievedItem],
    client: ObjectLookupInterface,
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


def _has_valid_credentials(config: RetrievalProviderConfig) -> bool:
    """
    Check if an endpoint has valid credentials based on its database type.

    Args:
        config: Endpoint configuration

    Returns:
        True if endpoint has required credentials
    """
    # Generic credential validation:
    # - If has database_path, assume local storage (always valid)
    # - Otherwise, check for api_endpoint (remote storage needs endpoint)
    # - api_key is optional for most providers
    if config.database_path:
        return True  # Local file-based storage
    elif config.api_endpoint:
        return True  # Remote storage with endpoint
    elif config.import_path:
        # If import_path is configured, assume it's valid (provider may not need credentials)
        return True
    else:
        return False


def _resolve_endpoint_name() -> str:
    """
    Resolve and validate the endpoint name.

    Returns:
        Validated endpoint name

    Raises:
        ValueError: If no valid endpoint found or specified endpoint invalid
    """
    app_config = get_config()
    for name, endpoint_cfg in app_config.retrieval_endpoints.items():
        if endpoint_cfg.enabled and _has_valid_credentials(endpoint_cfg):
            return name
    raise ValueError(
        "No endpoint specified and no enabled endpoints with valid credentials found"
    )


async def get_vectordb_client() -> VectorDBClientInterface:
    """
    Factory function to get or create a vector database client.

    This function handles endpoint validation, dynamic loading, and caching.

    Returns:
        VectorDBClientInterface instance (cached)

    Raises:
        ValueError: If endpoint invalid or missing credentials
    """
    # Resolve and validate endpoint
    endpoint_name = _resolve_endpoint_name()
    endpoint_config = get_config().retrieval_endpoints[endpoint_name]
    db_type = endpoint_config.db_type

    # Use cache key combining db_type and endpoint
    cache_key = f"{db_type}_{endpoint_name}"

    # Fast path - check cache without lock
    if cache_key in _client_cache:
        return _client_cache[cache_key]

    # Slow path - acquire per-key lock for client creation
    async with _client_cache_locks[cache_key]:
        # Double-check after acquiring lock (another task may have created it)
        if cache_key in _client_cache:
            return _client_cache[cache_key]

        # Create the appropriate client using config-driven dynamic import
        try:
            # Use preloaded module if available
            if db_type in _preloaded_modules:
                client_class = _preloaded_modules[db_type]
            # Otherwise use config to dynamically import
            elif endpoint_config.import_path and endpoint_config.class_name:
                # Dynamic import based on config
                import_path = endpoint_config.import_path
                class_name = endpoint_config.class_name
                module = importlib.import_module(import_path)
                client_class = getattr(module, class_name)
            else:
                error_msg = f"No import_path and class_name configured for: {db_type}"
                raise ValueError(error_msg)

            # Instantiate the client with endpoint configuration
            client = client_class(endpoint_config)
        except ImportError as e:
            raise ValueError(f"Failed to load client for {db_type}: {e}")

        # Store in cache and return
        _client_cache[cache_key] = client
        return client


def get_item_retriever() -> ItemRetriever:
    """
    Factory function to get the configured ItemRetriever instance.

    Returns:
        ItemRetriever instance (currently VectorDBRetriever)
    """
    from nlweb_core.vector_db_retriever import VectorDBRetriever

    return VectorDBRetriever()
