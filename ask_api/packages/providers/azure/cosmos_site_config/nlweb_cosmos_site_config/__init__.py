"""
Azure Cosmos DB provider for site configuration storage.
"""

from .site_config_lookup import CosmosSiteConfigLookup, generate_config_id

__all__ = ["CosmosSiteConfigLookup", "generate_config_id"]
