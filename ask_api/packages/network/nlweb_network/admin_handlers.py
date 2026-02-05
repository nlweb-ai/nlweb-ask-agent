# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Admin handlers for site config management API.

Provides REST endpoints for CRUD operations on site configurations.
"""

import logging
from aiohttp import web

logger = logging.getLogger(__name__)


def normalize_domain(domain: str) -> str:
    """
    Normalize domain name.

    - Lowercase
    - Strip whitespace
    - Remove 'www.' prefix

    Args:
        domain: Domain name (e.g., "example.com" or "www.example.com")

    Returns:
        Normalized domain name
    """
    normalized = domain.lower().strip()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


async def get_site_config_handler(request):
    """
    GET /site-configs/{domain}

    Retrieve all config types for a domain.
    """
    try:
        domain = request.match_info.get("domain")
        if not domain:
            return web.json_response({"error": "Domain parameter required"}, status=400)

        # Normalize domain
        domain = normalize_domain(domain)

        # Get site config lookup
        from nlweb_core.site_config import get_site_config_lookup

        lookup = get_site_config_lookup("default")

        if not lookup:
            return web.json_response(
                {"error": "Site config not configured"}, status=503
            )

        # Get full config
        result = await lookup.get_full_config(domain)

        if not result:
            return web.json_response(
                {"error": "Domain not found", "domain": domain}, status=404
            )

        return web.json_response(result, status=200)

    except Exception as e:
        logger.error(f"Error getting site config: {e}", exc_info=True)
        return web.json_response(
            {"error": "Internal server error", "details": str(e)}, status=500
        )


async def get_config_type_handler(request):
    """
    GET /site-configs/{domain}/{config_type}

    Retrieve a specific config type for a domain.
    """
    try:
        domain = request.match_info.get("domain")
        config_type = request.match_info.get("config_type")

        if not domain or not config_type:
            return web.json_response(
                {"error": "Domain and config_type parameters required"}, status=400
            )

        # Normalize domain
        domain = normalize_domain(domain)

        # Get site config lookup
        from nlweb_core.site_config import get_site_config_lookup

        lookup = get_site_config_lookup("default")

        if not lookup:
            return web.json_response(
                {"error": "Site config not configured"}, status=503
            )

        # Get specific config type
        result = await lookup.get_config_type(domain, config_type)

        if not result:
            return web.json_response(
                {
                    "error": "Config type not found",
                    "domain": domain,
                    "config_type": config_type,
                },
                status=404,
            )

        return web.json_response(result, status=200)

    except Exception as e:
        logger.error(f"Error getting config type: {e}", exc_info=True)
        return web.json_response(
            {"error": "Internal server error", "details": str(e)}, status=500
        )


async def update_config_type_handler(request):
    """
    PUT /site-configs/{domain}/{config_type}

    Create or update a specific config type for a domain.

    **IMPORTANT - Blind Write Behavior:**
    - Replaces the ENTIRE config_type with provided data
    - Other config types (elicitation, freshness_config, etc.) are NOT affected
    - Within this config_type, ALL previous data is REPLACED

    Example: Updating freshness_config

    Existing:
    {
      "freshness_config": {
        "recency_boost": {"enabled": true, "recency_weight": 0.15, "max_age_days": 90}
      }
    }

    PUT /site-configs/aajtak.in/freshness_config
    {
      "recency_boost": {"enabled": true, "recency_weight": 0.20}
    }

    Result:
    {
      "freshness_config": {
        "recency_boost": {"enabled": true, "recency_weight": 0.20}
        # max_age_days is GONE (not merged)
      }
    }

    To preserve fields, provide the complete config type in your request.
    """
    try:
        domain = request.match_info.get("domain")
        config_type = request.match_info.get("config_type")

        if not domain or not config_type:
            return web.json_response(
                {"error": "Domain and config_type parameters required"}, status=400
            )

        # Normalize domain
        domain = normalize_domain(domain)

        # Parse request body
        try:
            config_data = await request.json()
        except Exception as e:
            return web.json_response(
                {"error": "Invalid JSON", "details": str(e)}, status=400
            )

        # Get site config lookup
        from nlweb_core.site_config import get_site_config_lookup

        lookup = get_site_config_lookup("default")

        if not lookup:
            return web.json_response(
                {"error": "Site config not configured"}, status=503
            )

        # Update config type
        result = await lookup.update_config_type(domain, config_type, config_data)

        # Return appropriate status
        if result.get("created"):
            return web.json_response(
                {
                    "message": f"Site config created with {config_type}",
                    "domain": domain,
                    "config_type": config_type,
                    "id": result.get("id"),
                },
                status=201,
            )
        else:
            return web.json_response(
                {
                    "message": f"{config_type} config updated",
                    "domain": domain,
                    "config_type": config_type,
                },
                status=200,
            )

    except Exception as e:
        logger.error(f"Error updating config type: {e}", exc_info=True)
        return web.json_response(
            {"error": "Internal server error", "details": str(e)}, status=500
        )


async def delete_config_type_handler(request):
    """
    DELETE /site-configs/{domain}/{config_type}

    Remove a specific config type for a domain.
    If this is the last config type, the entire document is deleted.
    """
    try:
        domain = request.match_info.get("domain")
        config_type = request.match_info.get("config_type")

        if not domain or not config_type:
            return web.json_response(
                {"error": "Domain and config_type parameters required"}, status=400
            )

        # Normalize domain
        domain = normalize_domain(domain)

        # Get site config lookup
        from nlweb_core.site_config import get_site_config_lookup

        lookup = get_site_config_lookup("default")

        if not lookup:
            return web.json_response(
                {"error": "Site config not configured"}, status=503
            )

        # Delete config type
        result = await lookup.delete_config_type(domain, config_type)

        if not result:
            return web.json_response(
                {
                    "error": "Config type not found",
                    "domain": domain,
                    "config_type": config_type,
                },
                status=404,
            )

        # Check if entire domain was deleted
        if result.get("domain_deleted"):
            return web.json_response(
                {
                    "message": f"Last config type removed, domain deleted",
                    "domain": domain,
                    "config_type": config_type,
                },
                status=200,
            )
        else:
            return web.json_response(
                {
                    "message": f"{config_type} config deleted",
                    "domain": domain,
                    "config_type": config_type,
                },
                status=200,
            )

    except Exception as e:
        logger.error(f"Error deleting config type: {e}", exc_info=True)
        return web.json_response(
            {"error": "Internal server error", "details": str(e)}, status=500
        )


async def delete_site_config_handler(request):
    """
    DELETE /site-configs/{domain}

    Remove all config types for a domain (delete entire document).
    """
    try:
        domain = request.match_info.get("domain")

        if not domain:
            return web.json_response({"error": "Domain parameter required"}, status=400)

        # Normalize domain
        domain = normalize_domain(domain)

        # Get site config lookup
        from nlweb_core.site_config import get_site_config_lookup

        lookup = get_site_config_lookup("default")

        if not lookup:
            return web.json_response(
                {"error": "Site config not configured"}, status=503
            )

        # Delete full config
        result = await lookup.delete_full_config(domain)

        if not result:
            return web.json_response(
                {"error": "Domain not found", "domain": domain}, status=404
            )

        return web.json_response(
            {"message": "Site config deleted", "domain": domain}, status=200
        )

    except Exception as e:
        logger.error(f"Error deleting site config: {e}", exc_info=True)
        return web.json_response(
            {"error": "Internal server error", "details": str(e)}, status=500
        )
