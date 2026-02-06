"""
Base class for site configuration lookup providers.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional


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


