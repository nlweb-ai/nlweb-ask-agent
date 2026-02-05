"""
Base class for site configuration lookup providers.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from nlweb_core.config import SiteConfigStorageConfig, get_config
from nlweb_core.provider_map import ProviderMap

logger = logging.getLogger(__name__)


class SiteConfigLookup(ABC):
    """Abstract base class defining the interface for site configuration lookup providers."""

    @abstractmethod
    def __init__(self, **kwargs: Any) -> None:
        """Initialize the site config lookup provider."""
        ...

    @abstractmethod
    async def get_config(self, site: str) -> Optional[dict[str, Any]]:
        """Retrieve site configuration with caching.

        Args:
            site: Site filter (URL or domain, e.g., "yelp.com", "https://www.yelp.com")

        Returns:
            Configuration dict or None if not found
        """
        ...

    @abstractmethod
    async def get_config_type(self, site: str, config_type: str) -> Optional[Any]:
        """Retrieve a specific config type for a site.

        Args:
            site: Site filter (URL or domain, e.g., "yelp.com", "https://www.yelp.com")
            config_type: Config type name (e.g., "elicitation", "item_types")

        Returns:
            Configuration value or None if not found
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the client and release resources."""
        ...


# Provider map for site config lookups
_site_config_map: ProviderMap[SiteConfigLookup] = ProviderMap(
    config_getter=lambda name: get_config().get_site_config_provider(name),
    error_prefix="Site config provider",
)


def get_site_config_lookup(name: str) -> SiteConfigLookup:
    """Get site config lookup instance by name, creating it lazily if needed.

    Args:
        name: Provider name.

    Returns:
        SiteConfigLookup instance.

    Raises:
        ValueError: If provider is not configured.
    """
    return _site_config_map.get(name)


async def close_site_config_lookup() -> None:
    """Close all site config lookup clients and release resources."""
    await _site_config_map.close()


def initialize_site_config(
    site_config_providers: dict[str, SiteConfigStorageConfig],
) -> None:
    """
    Pre-initialize all configured site config lookups.

    This should be called during server startup to eagerly populate the cache.

    Args:
        site_config_providers: Mapping of site config provider names to configs.
    """
    for provider_name in site_config_providers:
        get_site_config_lookup(provider_name)
