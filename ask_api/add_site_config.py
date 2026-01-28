#!/usr/bin/env python
"""
DELETE LATER: Script to add site configurations to Cosmos DB for testing.

Usage:
    python add_site_config.py --domain yelp.com --config example_yelp_config.json
    python add_site_config.py --domain yelp.com --template restaurant
"""

import argparse
import json
import os
import sys
import hashlib
from dotenv import load_dotenv
from azure.cosmos import CosmosClient

# Load environment variables
load_dotenv()


def generate_config_id(domain: str) -> str:
    """
    Generate deterministic ID from domain using SHA-256.

    Args:
        domain: Domain name (e.g., "yelp.com")

    Returns:
        SHA-256 hash of normalized domain
    """
    normalized = domain.lower().strip()
    return hashlib.sha256(normalized.encode()).hexdigest()

# Example templates (using flat structure, no version field)
TEMPLATES = {
    "restaurant": {
        "intent_elicitations": [
            {
                "intent": {"value": "restaurant search"},
                "required_info": {"value": "location"}
            },
            {
                "intent": {"value": "recipe search"},
                "required_info": {"value": "cuisine or dish"}
            }
        ]
    },
    "recipe": {
        "intent_elicitations": [
            {
                "intent": {"value": "recipe search"},
                "required_info": {"value": "cuisine or dish"}
            }
        ]
    },
    "location_required": {
        "intent_elicitations": [
            {
                "intent": {},  # Universal - applies to ALL queries
                "required_info": {"value": "location"}
            }
        ]
    }
}


def get_cosmos_client():
    """
    Get Cosmos DB client from environment variables.

    Uses COSMOS_DB_ENDPOINT and COSMOS_DB_DATABASE_NAME by default (shared with object_storage).
    For partitioned setup, set different environment variables in your config.yaml.
    """
    endpoint = os.getenv('COSMOS_DB_ENDPOINT')
    database_name = os.getenv('COSMOS_DB_DATABASE_NAME')

    if not endpoint or not database_name:
        print("Error: Cosmos DB not configured!")
        print()
        print("Required environment variables:")
        print("  COSMOS_DB_ENDPOINT")
        print("  COSMOS_DB_DATABASE_NAME")
        print()
        print("These are the same variables used by object_storage (shared DB pattern).")
        print("For partitioned DB, set different variables and update config.yaml accordingly.")
        sys.exit(1)

    print(f"Using Cosmos DB for site configs:")
    print(f"  Endpoint: {endpoint}")
    print(f"  Database: {database_name}")
    print("  Auth: Azure Managed Identity")

    from azure.identity import DefaultAzureCredential
    credential = DefaultAzureCredential()
    client = CosmosClient(endpoint, credential=credential)

    database = client.get_database_client(database_name)
    container = database.get_container_client("site_configs")

    return container


def add_site_config(domain: str, config_data: dict):
    """Add or update a site configuration in Cosmos DB."""
    # Normalize domain
    normalized_domain = domain.lower().strip()
    if normalized_domain.startswith("www."):
        normalized_domain = normalized_domain[4:]

    # Generate deterministic ID
    config_id = generate_config_id(normalized_domain)

    # Create document with namespaced config structure
    # Format: {"config": {"elicitation": {...}, "scoring_specs": {...}}}
    document = {
        "id": config_id,
        "domain": normalized_domain,
        "config": {
            "elicitation": config_data  # Namespace under 'elicitation'
        },
        "_created": None,  # Cosmos will auto-generate
        "_updated": None   # Cosmos will auto-generate
    }

    # Get Cosmos container
    container = get_cosmos_client()

    # Upsert document
    try:
        result = container.upsert_item(document)
        print(f"✓ Site config added/updated successfully for domain: {normalized_domain}")
        print(f"  - Document ID: {config_id}")
        print(f"  - Partition key: {normalized_domain}")
        print(f"  - Intent-elicitation pairs: {len(config_data.get('intent_elicitations', []))}")
        return result
    except Exception as e:
        print(f"✗ Failed to add site config: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Add site configurations to Cosmos DB for testing"
    )
    parser.add_argument(
        "--domain",
        required=True,
        help="Domain name (e.g., yelp.com, www.yelp.com)"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--config",
        help="Path to JSON config file"
    )
    group.add_argument(
        "--template",
        choices=list(TEMPLATES.keys()),
        help="Use a predefined template (restaurant, recipe, location_required)"
    )

    args = parser.parse_args()

    # Load config
    if args.config:
        # Load from file
        try:
            with open(args.config, 'r') as f:
                config_data = json.load(f)
        except FileNotFoundError:
            print(f"Error: Config file not found: {args.config}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in config file: {e}")
            sys.exit(1)
    else:
        # Use template
        config_data = TEMPLATES[args.template]

    # Add to Cosmos DB
    print(f"Adding site config for domain: {args.domain}")
    print(f"Config: {json.dumps(config_data, indent=2)}")
    print()

    add_site_config(args.domain, config_data)


if __name__ == "__main__":
    main()
