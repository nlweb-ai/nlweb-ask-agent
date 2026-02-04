# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Azure Cosmos DB implementation for site configuration lookup.
Uses native async client for proper async/await support.
"""

import hashlib
import time
import logging
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
from azure.cosmos.aio import CosmosClient
from azure.cosmos import exceptions

from nlweb_core.azure_credentials import get_azure_credential
from nlweb_core.site_config import SiteConfigLookup

logger = logging.getLogger(__name__)


def generate_config_id(domain: str) -> str:
    """
    Generate deterministic ID from domain using SHA-256.

    Args:
        domain: Domain name (e.g., "yelp.com")

    Returns:
        SHA-256 hash of normalized domain
    """
    normalized = domain.lower().strip()
    return hashlib.sha256(normalized.encode()).hexdigest()


def normalize_domain(domain_or_url: str) -> str:
    """
    Normalize a domain or URL to a canonical domain name.

    Handles URLs by extracting the netloc, then lowercases, strips whitespace,
    and removes the www. prefix.

    Args:
        domain_or_url: Domain or URL (e.g., "https://www.yelp.com/biz", "WWW.Yelp.com ")

    Returns:
        Normalized domain (e.g., "yelp.com")

    Raises:
        ValueError: If URL parsing fails
    """
    value = domain_or_url.strip().lower()

    if value.startswith(("http://", "https://")):
        try:
            parsed = urlparse(value)
            value = parsed.netloc
        except Exception as e:
            logger.warning(f"Failed to parse as URL: {domain_or_url} - {e}")
            raise ValueError(f"Invalid URL: {domain_or_url}") from e

    if value.startswith("www."):
        value = value[4:]

    return value


class CosmosSiteConfigLookup(SiteConfigLookup):
    """
    Azure Cosmos DB implementation for site configuration lookup.
    Uses native async client for proper connection pooling.
    """

    def __init__(
        self,
        *,
        provider_name: str,
        endpoint: str,
        database_name: str,
        container_name: str,
        cache_ttl: int,
        **kwargs: Any,
    ):
        """
        Initialize Cosmos DB configuration. Client is created lazily on first use.

        Args:
            provider_name: Name of the site config provider.
            endpoint: Cosmos DB endpoint URL.
            database_name: Cosmos DB database name.
            container_name: Cosmos DB container name.
            cache_ttl: Cache TTL in seconds.
        """
        if kwargs:
            raise TypeError(
                f"CosmosSiteConfigLookup received unexpected arguments: {list(kwargs.keys())}"
            )

        self._provider_name = provider_name
        self._endpoint = endpoint
        self._database_name = database_name
        self._container_name = container_name
        self.cache_ttl = cache_ttl

        # Client initialized lazily on first use
        self._client: Optional[CosmosClient] = None
        self._container = None

        # Initialize cache
        self.cache: Dict[str, Dict[str, Any]] = {}

        logger.info(
            f"CosmosSiteConfigLookup initialized: endpoint={self._endpoint}, "
            f"database={self._database_name}, "
            f"container={self._container_name}, "
            f"cache_ttl={self.cache_ttl}s"
        )

    async def _ensure_client(self):
        """Create client if not already initialized."""
        if self._client is None:
            credential = await get_azure_credential()
            self._client = CosmosClient(
                self._endpoint,
                credential=credential,
            )
            database = self._client.get_database_client(self._database_name)
            self._container = database.get_container_client(self._container_name)

    async def _read_document(
        self, domain: str
    ) -> tuple[str, Optional[Dict[str, Any]]]:
        """
        Read config document for a domain from Cosmos DB with caching.

        Args:
            domain: Domain name or URL

        Returns:
            Tuple of (config_id, document or None if not found)
        """
        normalized = normalize_domain(domain)
        config_id = generate_config_id(normalized)

        # Check cache
        if normalized in self.cache:
            entry = self.cache[normalized]
            if time.time() - entry["timestamp"] < self.cache_ttl:
                return config_id, entry["document"]
            del self.cache[normalized]

        await self._ensure_client()
        assert self._container is not None

        try:
            item = await self._container.read_item(
                item=config_id, partition_key=normalized
            )
            self.cache[normalized] = {"document": item, "timestamp": time.time()}
            return config_id, item
        except exceptions.CosmosResourceNotFoundError:
            self.cache[normalized] = {"document": None, "timestamp": time.time()}
            return config_id, None

    async def get_config(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve elicitation config for a domain.

        Args:
            domain: Domain name (e.g., "yelp.com", "www.yelp.com")

        Returns:
            Elicitation config dict or None if not found
        """
        _, item = await self._read_document(domain)

        if not item:
            return None

        config = item.get("config", {})
        return config.get("elicitation")

    async def get_config_for_site_filter(
        self, site_filter: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve site configuration for a site filter (URL or domain).

        Args:
            site_filter: Site filter from query (e.g., "yelp.com", "https://www.yelp.com")

        Returns:
            Configuration dict or None if not found
        """
        if not site_filter:
            return None

        domain = normalize_domain(site_filter)
        return await self.get_config(domain)

    async def get_item_type_for_ranking(self, site_filter: str | None) -> str | None:
        """
        Get the primary item type for ranking purposes.

        This is a convenience method that returns the first configured item_type
        for a site, or the default value if not configured.

        Args:
            site_filter: Site filter from query (e.g., "yelp.com", "https://www.yelp.com")

        Returns:
            First item_type from config, or None
        """
        if not site_filter:
            return None

        normalized_domain = normalize_domain(site_filter)

        # Get item_types from config
        item_types = await self.get_config_type(normalized_domain, "item_types")

        if item_types and isinstance(item_types, list) and len(item_types) > 0:
            return item_types[0]

        return None

    def invalidate_cache(self, domain: Optional[str] = None):
        """
        Invalidate cache for a specific domain or entire cache.

        Args:
            domain: Domain to invalidate (None = invalidate all)
        """
        if domain:
            normalized_domain = normalize_domain(domain)
            if normalized_domain in self.cache:
                del self.cache[normalized_domain]
                logger.info(f"Cache invalidated for domain: {normalized_domain}")
        else:
            self.cache.clear()
            logger.info("Entire cache invalidated")

    async def prewarm_cache(self, domains: List[str]):
        """
        Pre-load configurations for popular domains on startup.

        Args:
            domains: List of domain names to pre-load
        """
        logger.info(f"Pre-warming cache for {len(domains)} domains")

        for domain in domains:
            try:
                await self.get_config(domain)
            except Exception as e:
                logger.warning(f"Failed to prewarm cache for {domain}: {e}")
                raise

        logger.info(f"Cache pre-warming complete: {len(self.cache)} configs loaded")

    async def get_full_config(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve full config document for a domain (all config types).

        Args:
            domain: Domain name (e.g., "yelp.com", "www.yelp.com")

        Returns:
            Full document dict or None if not found
        """
        _, item = await self._read_document(domain)
        return item

    async def get_config_type(
        self, domain: str, config_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific config type for a domain.

        Args:
            domain: Domain name (e.g., "yelp.com")
            config_type: Config type name (e.g., "elicitation", "scoring_specs")

        Returns:
            Config type dict or None if not found
        """
        _, item = await self._read_document(domain)

        if not item:
            return None

        config = item.get("config", {})
        return config.get(config_type)

    async def update_config_type(
        self,
        domain: str,
        config_type: Optional[str],
        config_data: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Create, update, or delete config for a domain.

        Args:
            domain: Domain name
            config_type: Config type name, or None to delete entire document
            config_data: Config data to write, or None to delete

        Returns:
            For writes: dict with 'created' flag and 'id'
            For deletes: dict with 'deleted' flag, or None if not found
        """
        normalized = normalize_domain(domain)
        config_id, item = await self._read_document(domain)
        assert self._container is not None

        # Delete entire document
        if config_type is None:
            if not item:
                return None
            await self._container.delete_item(item=config_id, partition_key=normalized)
            self.invalidate_cache(normalized)
            return {"deleted": True}

        # Delete specific config type
        if config_data is None:
            if not item:
                return None
            config = item.get("config", {})
            if config_type not in config:
                return None
            del config[config_type]
            if not config:
                await self._container.delete_item(
                    item=config_id, partition_key=normalized
                )
                self.invalidate_cache(normalized)
                return {"deleted": True, "domain_deleted": True}
            item["config"] = config
            await self._container.upsert_item(item)
            self.invalidate_cache(normalized)
            return {"deleted": True, "domain_deleted": False}

        # Write operation
        if item:
            if "config" not in item:
                item["config"] = {}
            item["config"][config_type] = config_data
            created = False
        else:
            item = {
                "id": config_id,
                "domain": normalized,
                "config": {config_type: config_data},
            }
            created = True

        await self._container.upsert_item(item)
        self.invalidate_cache(normalized)
        return {"created": created, "id": config_id}

    async def delete_config_type(
        self, domain: str, config_type: str
    ) -> Optional[Dict[str, Any]]:
        """Delete a specific config type for a domain."""
        return await self.update_config_type(domain, config_type, None)

    async def delete_full_config(self, domain: str) -> bool:
        """Delete entire config document for a domain."""
        result = await self.update_config_type(domain, None, None)
        return result is not None

    async def close(self):
        """Close the Cosmos client and release resources."""
        if self._client is not None:
            await self._client.close()
            self._client = None
        self._container = None
