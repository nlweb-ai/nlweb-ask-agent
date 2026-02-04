"""
Site-specific configuration module for NLWeb.

This module provides intent-based elicitation for domain-specific queries.
"""

import logging
from typing import Any, Optional, Protocol

from nlweb_core.config import SiteConfigStorageConfig

from .intent_detector import IntentDetector
from .elicitation_checker import ElicitationChecker
from .elicitation_handler import ElicitationHandler

logger = logging.getLogger(__name__)


class SiteConfigLookupProtocol(Protocol):
    """Protocol defining the interface for site configuration lookup providers."""

    async def get_config(self, domain: str) -> Optional[dict[str, Any]]:
        """Retrieve site configuration for a domain with caching."""
        ...

    async def get_config_for_site_filter(
        self, site_filter: Optional[str]
    ) -> Optional[dict[str, Any]]:
        """Retrieve site configuration for a site filter (URL or domain)."""
        ...

    async def get_item_type_for_ranking(self, site_filter: Optional[str]) -> str | None:
        """Get the primary item type for ranking purposes."""
        ...

    async def close(self) -> None:
        """Close the client and release resources."""
        ...


# Module-level cache for site config services
_site_config_lookups: dict[str, SiteConfigLookupProtocol] = {}
_elicitation_handler: ElicitationHandler | None = None


def get_site_config_lookup(name: str) -> SiteConfigLookupProtocol | None:
    """Get the cached site config lookup instance by name.

    Args:
        name: Provider name.
    """
    if name in _site_config_lookups:
        return _site_config_lookups[name]
    return None


def get_elicitation_handler() -> ElicitationHandler | None:
    """Get the cached elicitation handler instance."""
    return _elicitation_handler


def set_elicitation_handler(handler: ElicitationHandler | None) -> None:
    """Set the elicitation handler (called at server startup)."""
    global _elicitation_handler
    _elicitation_handler = handler


async def close_site_config_lookup() -> None:
    """Close all site config lookup clients and release resources."""
    global _site_config_lookups
    for name, lookup in list(_site_config_lookups.items()):
        try:
            await lookup.close()
        except Exception as e:
            logger.warning(f"Error closing site config lookup '{name}': {e}")
    _site_config_lookups.clear()


__all__ = [
    "IntentDetector",
    "ElicitationChecker",
    "ElicitationHandler",
    "SiteConfigLookupProtocol",
    "initialize_site_config",
    "get_site_config_lookup",
    "get_elicitation_handler",
    "close_site_config_lookup",
]


def initialize_site_config(
    site_config_providers: dict[str, SiteConfigStorageConfig],
):
    """
    Initialize site config lookups from provider configs.

    This should be called during server startup.

    Args:
        site_config_providers: Mapping of site config provider names to configs.
    """
    # Initialize each configured provider
    for provider_name, provider_config in site_config_providers.items():
        # Validate required configuration
        if not provider_config.endpoint:
            raise ValueError(
                f"Site config provider '{provider_name}' missing endpoint configuration"
            )

        if not provider_config.database_name:
            raise ValueError(
                f"Site config provider '{provider_name}' missing database_name configuration"
            )

        # Create SiteConfigLookup using provider pattern
        try:

            module = __import__(
                provider_config.import_path, fromlist=[provider_config.class_name]
            )
            provider_class = getattr(module, provider_config.class_name)

            # Instantiate the provider, passing the provider name
            site_config_lookup = provider_class(provider_name=provider_name)

            logger.info(
                f"SiteConfigLookup '{provider_name}' initialized via provider: {provider_config.import_path}.{provider_config.class_name}"
            )

            # Store in module-level cache for access by handlers
            _site_config_lookups[provider_name] = site_config_lookup

        except Exception as e:
            logger.error(
                f"Failed to initialize SiteConfigLookup '{provider_name}': {e}",
                exc_info=True,
            )
            raise


def initialize_elicitation_handler() -> None:
    """
    Initialize the ElicitationHandler instance.
    """
    # Create ElicitationHandler (uses ask_llm_parallel with scoring model)
    try:
        elicitation_handler = ElicitationHandler()

        logger.info("ElicitationHandler initialized")

        # Store in module-level cache for access by handlers
        set_elicitation_handler(elicitation_handler)

    except Exception as e:
        logger.error(f"Failed to initialize ElicitationHandler: {e}", exc_info=True)
        raise
