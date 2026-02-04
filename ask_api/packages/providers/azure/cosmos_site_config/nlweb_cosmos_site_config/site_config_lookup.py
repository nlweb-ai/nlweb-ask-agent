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

    async def get_config(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve site configuration for a domain with caching.

        Args:
            domain: Domain name (e.g., "yelp.com", "www.yelp.com")

        Returns:
            Configuration dict or None if not found
        """
        # Normalize domain
        normalized_domain = domain.lower().strip()

        # Remove www. prefix if present (treat www.example.com same as example.com)
        if normalized_domain.startswith("www."):
            normalized_domain = normalized_domain[4:]

        # Check cache
        cache_key = normalized_domain
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            if time.time() - entry["timestamp"] < self.cache_ttl:
                logger.debug(f"Cache hit for domain: {normalized_domain}")
                return entry["config"]
            else:
                # Cache expired
                logger.debug(f"Cache expired for domain: {normalized_domain}")
                del self.cache[cache_key]

        await self._ensure_client()
        assert self._container is not None

        # Cosmos DB lookup
        config_id = generate_config_id(normalized_domain)

        try:
            logger.debug(
                f"Fetching config from Cosmos DB: domain={normalized_domain}, "
                f"id={config_id}"
            )

            item = await self._container.read_item(
                item=config_id, partition_key=normalized_domain
            )

            config = item.get("config")
            if not config:
                logger.warning(
                    f"Config document found but no 'config' field: domain={normalized_domain}"
                )
                return None

            # Get elicitation config from namespaced structure
            # Document format: {"config": {"elicitation": {...}, "scoring_specs": {...}}}
            elicitation_config = config.get("elicitation")

            if not elicitation_config:
                logger.warning(
                    f"No elicitation config found for domain: {normalized_domain}"
                )
                return None

            # Cache result (store elicitation config)
            self.cache[cache_key] = {
                "config": elicitation_config,
                "timestamp": time.time(),
            }

            logger.info(f"Elicitation config loaded for domain: {normalized_domain}")
            return elicitation_config

        except exceptions.CosmosResourceNotFoundError:
            logger.debug(f"No config found for domain: {normalized_domain}")
            # Cache negative result with shorter TTL (1 minute)
            self.cache[cache_key] = {"config": None, "timestamp": time.time()}
            return None

        except Exception as e:
            logger.error(
                f"Error fetching config for domain {normalized_domain}: {e}",
                exc_info=True,
            )
            raise

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

        site_filter = site_filter.strip().lower()

        # If it looks like a URL, parse it to extract domain
        if site_filter.startswith(("http://", "https://")):
            try:
                parsed = urlparse(site_filter)
                domain = parsed.netloc
            except Exception as e:
                logger.warning(
                    f"Failed to parse site filter as URL: {site_filter} - {e}"
                )
                raise
        else:
            domain = site_filter

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

        site_filter = site_filter.strip().lower()

        # Extract domain from URL if needed
        if site_filter.startswith(("http://", "https://")):
            try:
                parsed = urlparse(site_filter)
                domain = parsed.netloc
            except Exception as e:
                logger.warning(
                    f"Failed to parse site filter as URL: {site_filter} - {e}"
                )
                raise
        else:
            domain = site_filter

        # Normalize domain
        normalized_domain = domain.lower().strip()
        if normalized_domain.startswith("www."):
            normalized_domain = normalized_domain[4:]

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
            normalized_domain = domain.lower().strip()
            if normalized_domain.startswith("www."):
                normalized_domain = normalized_domain[4:]

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
        # Normalize domain
        normalized_domain = domain.lower().strip()
        if normalized_domain.startswith("www."):
            normalized_domain = normalized_domain[4:]

        await self._ensure_client()
        assert self._container is not None

        # Generate config ID
        config_id = generate_config_id(normalized_domain)

        try:
            logger.debug(
                f"Fetching full config from Cosmos DB: domain={normalized_domain}, "
                f"id={config_id}"
            )

            item = await self._container.read_item(
                item=config_id, partition_key=normalized_domain
            )

            logger.info(f"Full config loaded for domain: {normalized_domain}")
            return item

        except exceptions.CosmosResourceNotFoundError:
            logger.debug(f"No config found for domain: {normalized_domain}")
            return None

        except Exception as e:
            logger.error(
                f"Error fetching full config for domain {normalized_domain}: {e}",
                exc_info=True,
            )
            raise e

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
        # Normalize domain
        normalized_domain = domain.lower().strip()
        if normalized_domain.startswith("www."):
            normalized_domain = normalized_domain[4:]

        await self._ensure_client()
        assert self._container is not None

        # Generate config ID
        config_id = generate_config_id(normalized_domain)

        try:
            logger.debug(
                f"Fetching {config_type} config from Cosmos DB: domain={normalized_domain}"
            )

            item = await self._container.read_item(
                item=config_id, partition_key=normalized_domain
            )

            config = item.get("config", {})
            config_type_data = config.get(config_type)

            if not config_type_data:
                logger.debug(
                    f"No {config_type} config found for domain: {normalized_domain}"
                )
                return None

            logger.info(f"{config_type} config loaded for domain: {normalized_domain}")
            return config_type_data

        except exceptions.CosmosResourceNotFoundError:
            logger.debug(f"No config found for domain: {normalized_domain}")
            return None

        except Exception as e:
            logger.error(
                f"Error fetching {config_type} config for domain {normalized_domain}: {e}",
                exc_info=True,
            )
            raise

    async def update_config_type(
        self, domain: str, config_type: str, config_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create or update a specific config type for a domain.
        Replaces the config type entirely (blind write).
        Other config types remain unchanged.

        Args:
            domain: Domain name
            config_type: Config type name (e.g., "elicitation")
            config_data: Config data to write

        Returns:
            Result dict with 'created' flag and 'id'
        """
        # Normalize domain
        normalized_domain = domain.lower().strip()
        if normalized_domain.startswith("www."):
            normalized_domain = normalized_domain[4:]

        await self._ensure_client()
        assert self._container is not None

        # Generate config ID
        config_id = generate_config_id(normalized_domain)

        try:
            # Try to read existing document
            item = await self._container.read_item(
                item=config_id, partition_key=normalized_domain
            )

            # Update specific config type
            if "config" not in item:
                item["config"] = {}

            item["config"][config_type] = config_data

            # Upsert
            await self._container.upsert_item(item)

            # Invalidate cache for this domain
            self.invalidate_cache(normalized_domain)

            logger.info(f"{config_type} config updated for domain: {normalized_domain}")

            return {"created": False, "id": config_id}

        except exceptions.CosmosResourceNotFoundError:
            # Create new document
            item = {
                "id": config_id,
                "domain": normalized_domain,
                "config": {config_type: config_data},
            }

            await self._container.upsert_item(item)

            # Invalidate cache for this domain
            self.invalidate_cache(normalized_domain)

            logger.info(
                f"New site config created with {config_type} for domain: {normalized_domain}"
            )

            return {"created": True, "id": config_id}

        except Exception as e:
            logger.error(
                f"Error updating {config_type} config for domain {normalized_domain}: {e}",
                exc_info=True,
            )
            raise

    async def delete_config_type(
        self, domain: str, config_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Delete a specific config type for a domain.
        If this is the last config type, the entire document is deleted.

        Args:
            domain: Domain name
            config_type: Config type name (e.g., "elicitation")

        Returns:
            Result dict with 'domain_deleted' flag, or None if not found
        """
        # Normalize domain
        normalized_domain = domain.lower().strip()
        if normalized_domain.startswith("www."):
            normalized_domain = normalized_domain[4:]

        await self._ensure_client()
        assert self._container is not None

        # Generate config ID
        config_id = generate_config_id(normalized_domain)

        try:
            # Read existing document
            item = await self._container.read_item(
                item=config_id, partition_key=normalized_domain
            )

            config = item.get("config", {})

            # Check if config type exists
            if config_type not in config:
                logger.debug(
                    f"{config_type} config not found for domain: {normalized_domain}"
                )
                return None

            # Remove config type
            del config[config_type]

            # If config is now empty, delete entire document
            if not config:
                await self._container.delete_item(
                    item=config_id, partition_key=normalized_domain
                )

                # Invalidate cache for this domain
                self.invalidate_cache(normalized_domain)

                logger.info(
                    f"Last config type removed, domain deleted: {normalized_domain}"
                )

                return {"domain_deleted": True}

            # Otherwise, update document with remaining config types
            item["config"] = config
            await self._container.upsert_item(item)

            # Invalidate cache for this domain
            self.invalidate_cache(normalized_domain)

            logger.info(f"{config_type} config deleted for domain: {normalized_domain}")

            return {"domain_deleted": False}

        except exceptions.CosmosResourceNotFoundError:
            logger.debug(f"No config found for domain: {normalized_domain}")
            return None

        except Exception as e:
            logger.error(
                f"Error deleting {config_type} config for domain {normalized_domain}: {e}",
                exc_info=True,
            )
            raise

    async def delete_full_config(self, domain: str) -> bool:
        """
        Delete all config types for a domain (delete entire document).

        Args:
            domain: Domain name

        Returns:
            True if deleted, False if not found
        """
        # Normalize domain
        normalized_domain = domain.lower().strip()
        if normalized_domain.startswith("www."):
            normalized_domain = normalized_domain[4:]

        await self._ensure_client()
        assert self._container is not None

        # Generate config ID
        config_id = generate_config_id(normalized_domain)

        try:
            # Delete document
            await self._container.delete_item(
                item=config_id, partition_key=normalized_domain
            )

            # Invalidate cache for this domain
            self.invalidate_cache(normalized_domain)

            logger.info(f"Full config deleted for domain: {normalized_domain}")

            return True

        except exceptions.CosmosResourceNotFoundError:
            logger.debug(f"No config found for domain: {normalized_domain}")
            return False

        except Exception as e:
            logger.error(
                f"Error deleting full config for domain {normalized_domain}: {e}",
                exc_info=True,
            )
            raise

    async def close(self):
        """Close the Cosmos client and release resources."""
        if self._client is not None:
            await self._client.close()
            self._client = None
        self._container = None
