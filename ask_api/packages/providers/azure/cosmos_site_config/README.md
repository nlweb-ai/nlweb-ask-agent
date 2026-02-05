# NLWeb Azure Cosmos DB Site Config Provider

Azure Cosmos DB provider for site-specific configuration storage and lookup.

## Overview

This provider implements site configuration lookup using Azure Cosmos DB, enabling domain-specific query elicitation based on intents and required information checks.

## Features

- **Cosmos DB Integration**: Stores site configs in dedicated `site_configs` container
- **In-Memory Caching**: 5-minute TTL cache for fast lookups
- **Azure AD Support**: Managed Identity or API key authentication
- **Domain Normalization**: Handles www. prefix automatically

## Configuration

Configure in your `config.yaml`:

```yaml
site_config:
  default:
    endpoint_env: COSMOS_DB_ENDPOINT
    api_key_env: COSMOS_DB_KEY
    database_name_env: COSMOS_DB_DATABASE_NAME
    container_name: site_configs
    use_managed_identity: false
    cache_ttl: 300
```

## Usage

The provider is automatically initialized when site_config is configured:

```python
from nlweb_cosmos_site_config import CosmosSiteConfigLookup

# Initialized automatically from config via ProviderMap
# Direct instantiation example:
lookup = CosmosSiteConfigLookup(
    endpoint="https://your-cosmos.documents.azure.com",
    database_name="your-db",
    container_name="site_configs",
    cache_ttl=300,
)

# Get full config for a domain (all config types)
config = await lookup.get_config("yelp.com")

# Get a specific config type
elicitation = await lookup.get_config_type("yelp.com", "elicitation")
```

## Installation

```bash
pip install -e .
```

## License

MIT License - Copyright (c) 2025 Microsoft Corporation
