"""
Site-specific configuration module for NLWeb.

This module provides intent-based elicitation for domain-specific queries.
"""

import logging

from .base import (
    SiteConfigLookup,
    close_site_config_lookup,
    get_site_config_lookup,
    initialize_site_config,
)
from .elicitation_checker import ElicitationChecker
from .elicitation_handler import ElicitationHandler
from .intent_detector import IntentDetector
from .static_site_config import StaticSiteConfigLookup

logger = logging.getLogger(__name__)


_elicitation_handler: ElicitationHandler | None = None


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
    "SiteConfigLookup",
    "StaticSiteConfigLookup",
    "initialize_site_config",
    "get_site_config_lookup",
    "get_elicitation_handler",
    "close_site_config_lookup",
]


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
