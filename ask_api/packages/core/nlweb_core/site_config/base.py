"""
Base class for site configuration lookup providers.
"""

import importlib
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from nlweb_core.config import SiteConfigStorageConfig

logger = logging.getLogger(__name__)


class SiteConfigLookup(ABC):
    """Abstract base class defining the interface for site configuration lookup providers."""

    @abstractmethod
    async def get_config(self, domain: str) -> Optional[dict[str, Any]]:
        """Retrieve site configuration for a domain with caching.

        Args:
            domain: Domain name (e.g., "yelp.com", "www.yelp.com")

        Returns:
            Configuration dict or None if not found
        """
        ...

    @abstractmethod
    async def get_config_for_site_filter(
        self, site_filter: Optional[str]
    ) -> Optional[dict[str, Any]]:
        """Retrieve site configuration for a site filter (URL or domain).

        Args:
            site_filter: Site filter from query (e.g., "yelp.com", "https://www.yelp.com")

        Returns:
            Configuration dict or None if not found
        """
        ...

    @abstractmethod
    async def get_item_type_for_ranking(self, site_filter: Optional[str]) -> str | None:
        """Get the primary item type for ranking purposes.

        Args:
            site_filter: Site filter from query (e.g., "yelp.com", "https://www.yelp.com")

        Returns:
            First item_type from config, or None
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the client and release resources."""
        ...


# Module-level cache for site config services
_site_config_lookups: dict[str, SiteConfigLookup] = {}


def get_site_config_lookup(name: str) -> SiteConfigLookup | None:
    """Get the cached site config lookup instance by name.

    Args:
        name: Provider name.
    """
    if name in _site_config_lookups:
        return _site_config_lookups[name]
    return None


async def close_site_config_lookup() -> None:
    """Close all site config lookup clients and release resources."""
    global _site_config_lookups
    for name, lookup in list(_site_config_lookups.items()):
        try:
            await lookup.close()
        except Exception as e:
            logger.warning(f"Error closing site config lookup '{name}': {e}")
    _site_config_lookups.clear()


def initialize_site_config(
    site_config_providers: dict[str, SiteConfigStorageConfig],
) -> None:
    """
    Initialize site config lookups from provider configs.

    This should be called during server startup.

    Args:
        site_config_providers: Mapping of site config provider names to configs.
    """
    for provider_name, provider_config in site_config_providers.items():
        if not provider_config.endpoint:
            raise ValueError(
                f"Site config provider '{provider_name}' missing endpoint configuration"
            )

        if not provider_config.database_name:
            raise ValueError(
                f"Site config provider '{provider_name}' missing database_name configuration"
            )

        try:
            module = importlib.import_module(provider_config.import_path)
            provider_class = getattr(module, provider_config.class_name)

            site_config_lookup = provider_class(provider_name=provider_name)

            logger.info(
                f"SiteConfigLookup '{provider_name}' initialized via provider: "
                f"{provider_config.import_path}.{provider_config.class_name}"
            )

            _site_config_lookups[provider_name] = site_config_lookup

        except Exception as e:
            logger.error(
                f"Failed to initialize SiteConfigLookup '{provider_name}': {e}",
                exc_info=True,
            )
            raise
