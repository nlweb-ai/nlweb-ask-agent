"""
Base class for site configuration lookup providers.
"""

import importlib
import logging
import threading
from abc import ABC, abstractmethod
from typing import Any, Optional

from nlweb_core.config import SiteConfigStorageConfig, get_config

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


# Module-level cache for site config services
_site_config_lookups: dict[str, SiteConfigLookup] = {}
_site_config_lock = threading.Lock()


def get_site_config_lookup(name: str) -> SiteConfigLookup:
    """Get site config lookup instance by name, creating it lazily if needed.

    Args:
        name: Provider name.

    Returns:
        SiteConfigLookup instance.

    Raises:
        ValueError: If provider is not configured.
    """
    with _site_config_lock:
        if name in _site_config_lookups:
            return _site_config_lookups[name]

        config = get_config()
        provider_config = config.get_site_config_provider(name)
        if provider_config is None:
            raise ValueError(f"Site config provider '{name}' is not configured")

        try:
            module = importlib.import_module(provider_config.import_path)
            provider_class: type[SiteConfigLookup] = getattr(
                module, provider_config.class_name
            )
            lookup = provider_class(provider_name=name, **provider_config.options)

            logger.info(
                f"SiteConfigLookup '{name}' initialized via provider: "
                f"{provider_config.import_path}.{provider_config.class_name}"
            )

            _site_config_lookups[name] = lookup
            return lookup
        except Exception as e:
            logger.error(
                f"Failed to initialize SiteConfigLookup '{name}': {e}",
                exc_info=True,
            )
            raise


async def close_site_config_lookup() -> None:
    """Close all site config lookup clients and release resources."""
    with _site_config_lock:
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
    Pre-initialize all configured site config lookups.

    This should be called during server startup to eagerly populate the cache.

    Args:
        site_config_providers: Mapping of site config provider names to configs.
    """
    for provider_name in site_config_providers:
        get_site_config_lookup(provider_name)
