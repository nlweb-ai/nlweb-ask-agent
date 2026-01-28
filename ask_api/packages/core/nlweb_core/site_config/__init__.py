"""
Site-specific configuration module for NLWeb.

This module provides intent-based elicitation for domain-specific queries.
"""

import logging
from typing import Any, Optional, Protocol

from .intent_detector import IntentDetector
from .elicitation_checker import ElicitationChecker
from .elicitation_handler import ElicitationHandler

logger = logging.getLogger(__name__)


class SiteConfigLookupProtocol(Protocol):
    """Protocol defining the interface for site configuration lookup providers."""

    def get_config(self, domain: str) -> Optional[dict[str, Any]]:
        """Retrieve site configuration for a domain with caching."""
        ...

    def get_config_for_site_filter(
        self, site_filter: Optional[str]
    ) -> Optional[dict[str, Any]]:
        """Retrieve site configuration for a site filter (URL or domain)."""
        ...

    def get_item_type_for_ranking(self, site_filter: Optional[str]) -> str | None:
        """Get the primary item type for ranking purposes."""
        ...


# Module-level cache for site config services
_site_config_lookup: SiteConfigLookupProtocol | None = None
_elicitation_handler: ElicitationHandler | None = None


def get_site_config_lookup() -> SiteConfigLookupProtocol | None:
    """Get the cached site config lookup instance."""
    return _site_config_lookup


def set_site_config_lookup(lookup: SiteConfigLookupProtocol | None) -> None:
    """Set the site config lookup (called at server startup)."""
    global _site_config_lookup
    _site_config_lookup = lookup


def get_elicitation_handler() -> ElicitationHandler | None:
    """Get the cached elicitation handler instance."""
    return _elicitation_handler


def set_elicitation_handler(handler: ElicitationHandler | None) -> None:
    """Set the elicitation handler (called at server startup)."""
    global _elicitation_handler
    _elicitation_handler = handler


__all__ = [
    "IntentDetector",
    "ElicitationChecker",
    "ElicitationHandler",
    "SiteConfigLookupProtocol",
    "initialize_site_config",
    "get_site_config_lookup",
    "get_elicitation_handler",
]


def initialize_site_config(config) -> Optional[ElicitationHandler]:
    """
    Initialize site config lookup and elicitation handler from application config.

    This should be called during server startup.

    Args:
        config: AppConfig instance with site_config settings

    Returns:
        ElicitationHandler instance or None if site config is disabled
    """
    # Check if site config is enabled
    site_config = getattr(config, "site_config", None)
    if not site_config or not site_config.enabled:
        logger.info("Site config disabled - elicitation will not be available")
        return None

    # Validate required configuration
    if not site_config.endpoint:
        logger.warning("Site config enabled but endpoint not configured")
        return None

    if not site_config.database_name:
        logger.warning("Site config enabled but database_name not configured")
        return None

    # Create SiteConfigLookup using provider pattern
    try:
        # Dynamically import the provider class
        # Default to Azure Cosmos provider if not specified
        import_path = "nlweb_cosmos_site_config.site_config_lookup"
        class_name = "SiteConfigLookup"

        module = __import__(import_path, fromlist=[class_name])
        provider_class = getattr(module, class_name)

        # Instantiate the provider (it reads from CONFIG.site_config)
        site_config_lookup = provider_class()

        logger.info(
            f"SiteConfigLookup initialized via provider: {import_path}.{class_name}"
        )

        # Store in module-level cache for access by handlers
        set_site_config_lookup(site_config_lookup)

    except Exception as e:
        logger.error(f"Failed to initialize SiteConfigLookup: {e}", exc_info=True)
        return None

    # Create ElicitationHandler (uses ask_llm_parallel with scoring model)
    try:
        elicitation_handler = ElicitationHandler()

        logger.info("ElicitationHandler initialized")

        # Store in module-level cache for access by handlers
        set_elicitation_handler(elicitation_handler)

        return elicitation_handler

    except Exception as e:
        logger.error(f"Failed to initialize ElicitationHandler: {e}", exc_info=True)
        return None
