# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Azure Cosmos DB implementation for site configuration lookup.
Uses native async client for proper async/await support.
"""

import hashlib
import time
import logging
from typing import Optional, Dict, Any
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
        endpoint: str,
        database_name: str,
        container_name: str,
        cache_ttl: int,
        **kwargs: Any,
    ):
        """
        Initialize Cosmos DB configuration. Client is created lazily on first use.

        Args:
            endpoint: Cosmos DB endpoint URL.
            database_name: Cosmos DB database name.
            container_name: Cosmos DB container name.
            cache_ttl: Cache TTL in seconds.
        """
        if kwargs:
            raise TypeError(
                f"CosmosSiteConfigLookup received unexpected arguments: {list(kwargs.keys())}"
            )

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

    async def _read_config(self, site: str) -> Optional[Dict[str, Any]]:
        """
        Read config for a site from Cosmos DB with caching.

        Args:
            site: Site filter (URL or domain)

        Returns:
            Config dict or None if not found
        """
        normalized = normalize_domain(site)
        config_id = generate_config_id(normalized)

        # Check cache
        if normalized in self.cache:
            entry = self.cache[normalized]
            if time.time() - entry["timestamp"] < self.cache_ttl:
                return entry["config"]
            del self.cache[normalized]

        await self._ensure_client()
        assert self._container is not None

        try:
            item = await self._container.read_item(
                item=config_id, partition_key=normalized
            )
            config = item.get("config", {})
            self.cache[normalized] = {"config": config, "timestamp": time.time()}
            return config
        except exceptions.CosmosResourceNotFoundError:
            self.cache[normalized] = {"config": None, "timestamp": time.time()}
            return None

    async def get_config(self, site: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve full config for a site (all config types).

        Args:
            site: Site filter (URL or domain, e.g., "yelp.com", "https://www.yelp.com")

        Returns:
            Config dict with all config types, or None if not found
        """
        return await self._read_config(site)

    def _invalidate_cache(self, site: Optional[str] = None):
        """
        Invalidate cache for a specific site or entire cache.

        Args:
            site: Site to invalidate (None = invalidate all)
        """
        if site:
            normalized = normalize_domain(site)
            if normalized in self.cache:
                del self.cache[normalized]
                logger.info(f"Cache invalidated for site: {normalized}")
        else:
            self.cache.clear()
            logger.info("Entire cache invalidated")

    async def get_config_type(
        self, site: str, config_type: str
    ) -> Optional[Any]:
        """
        Retrieve a specific config type for a site.

        Args:
            site: Site filter (URL or domain, e.g., "yelp.com", "https://www.yelp.com")
            config_type: Config type name (e.g., "elicitation", "scoring_specs")

        Returns:
            Config type dict or None if not found
        """
        config = await self._read_config(site)
        if not config:
            return None
        return config.get(config_type)

    async def _delete_config(self, site: str) -> bool:
        """
        Delete a config document from Cosmos DB.

        Args:
            site: Site filter (URL or domain)

        Returns:
            True if deleted, False if not found
        """
        normalized = normalize_domain(site)
        config_id = generate_config_id(normalized)

        await self._ensure_client()
        assert self._container is not None

        try:
            await self._container.delete_item(item=config_id, partition_key=normalized)
            self._invalidate_cache(site)
            return True
        except exceptions.CosmosResourceNotFoundError:
            return False

    async def _write_config(self, site: str, config: Dict[str, Any]) -> str:
        """
        Write a config document to Cosmos DB.

        Args:
            site: Site filter (URL or domain)
            config: Config dict with all config types

        Returns:
            The config_id of the written document
        """
        normalized = normalize_domain(site)
        config_id = generate_config_id(normalized)

        item = {
            "id": config_id,
            "domain": normalized,
            "config": config,
        }

        await self._ensure_client()
        assert self._container is not None
        await self._container.upsert_item(item)
        self._invalidate_cache(site)
        return config_id

    async def update_config_type(
        self,
        site: str,
        config_type: Optional[str],
        config_data: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Create, update, or delete config for a site.

        Args:
            site: Site filter (URL or domain)
            config_type: Config type name, or None to delete entire document
            config_data: Config data to write, or None to delete

        Returns:
            For writes: dict with 'created' flag and 'id'
            For deletes: dict with 'deleted' flag, or None if not found
        """
        config = await self._read_config(site)

        # Delete entire document
        if config_type is None:
            if config is None:
                return None
            await self._delete_config(site)
            return {"deleted": True}

        # Delete specific config type
        if config_data is None:
            if config is None:
                return None
            if config_type not in config:
                return None
            del config[config_type]
            if not config:
                await self._delete_config(site)
                return {"deleted": True, "domain_deleted": True}
            await self._write_config(site, config)
            return {"deleted": True, "domain_deleted": False}

        # Write operation
        created = config is None
        if config is None:
            config = {}
        config[config_type] = config_data
        config_id = await self._write_config(site, config)
        return {"created": created, "id": config_id}

    async def delete_config_type(
        self, site: str, config_type: str
    ) -> Optional[Dict[str, Any]]:
        """Delete a specific config type for a site."""
        return await self.update_config_type(site, config_type, None)

    async def delete_full_config(self, site: str) -> bool:
        """Delete entire config document for a site."""
        result = await self.update_config_type(site, None, None)
        return result is not None

    async def close(self):
        """Close the Cosmos client and release resources."""
        if self._client is not None:
            await self._client.close()
            self._client = None
        self._container = None
