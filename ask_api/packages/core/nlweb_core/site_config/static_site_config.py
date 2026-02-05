"""
Static site configuration lookup provider.

Reads site configurations directly from config.yaml kwargs.
"""

import logging
from typing import Any, Optional
from urllib.parse import urlparse

from .base import SiteConfigLookup

logger = logging.getLogger(__name__)


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


class StaticSiteConfigLookup(SiteConfigLookup):
    """
    Static site configuration lookup provider.

    Reads site configurations from config.yaml kwargs, allowing inline
    definition of site configs without external storage.
    """

    def __init__(
        self,
        *,
        sites: dict[str, dict[str, Any]],
        **kwargs: Any,
    ):
        """
        Initialize static site config lookup.

        Args:
            sites: Map of domain -> config dict. Keys can be domains or URLs
                   (will be normalized). Values are config dicts with config
                   types as keys (e.g., {"elicitation": {...}, "item_types": [...]}).
        """
        if kwargs:
            raise TypeError(
                f"StaticSiteConfigLookup received unexpected arguments: {list(kwargs.keys())}"
            )

        # Normalize all site keys at init time for efficient lookups
        self._sites: dict[str, dict[str, Any]] = {}
        for site_key, config in sites.items():
            normalized = normalize_domain(site_key)
            self._sites[normalized] = config

        logger.info(
            f"StaticSiteConfigLookup initialized with {len(self._sites)} site(s): "
            f"{list(self._sites.keys())}"
        )

    async def get_config(self, site: str) -> Optional[dict[str, Any]]:
        """
        Retrieve full config for a site (all config types).

        Args:
            site: Site filter (URL or domain, e.g., "yelp.com", "https://www.yelp.com")

        Returns:
            Config dict with all config types, or None if not found
        """
        normalized = normalize_domain(site)
        return self._sites.get(normalized)

    async def get_config_type(self, site: str, config_type: str) -> Optional[Any]:
        """
        Retrieve a specific config type for a site.

        Args:
            site: Site filter (URL or domain, e.g., "yelp.com", "https://www.yelp.com")
            config_type: Config type name (e.g., "elicitation", "scoring_specs")

        Returns:
            Config type value or None if not found
        """
        config = await self.get_config(site)
        if not config:
            return None
        return config.get(config_type)

    async def close(self) -> None:
        """Close the provider (no-op for static config)."""
        pass
