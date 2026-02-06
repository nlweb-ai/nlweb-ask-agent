#!/usr/bin/env python3
"""
Script to add recency boost configuration for sites.

This script provides a convenient CLI with presets and validation.
For programmatic/automated access, use the REST API instead:
  PUT /site-configs/{domain}/freshness_config

Usage:
    python add_recency_boost_config.py aajtak.in --preset news
    python add_recency_boost_config.py news18.com --recency-weight 0.20
    python add_recency_boost_config.py blog.example.com --decay-rate 0.05 --max-age-days 180
"""

import argparse
import asyncio
import sys


async def add_recency_config(
    domain: str,
    enabled: bool = True,
    recency_weight: float = 0.15,
    decay_rate: float = 0.1,
    max_age_days: int = 90,
):
    """
    Add recency boost configuration for a domain.

    Args:
        domain: Domain name (e.g., "aajtak.in")
        enabled: Enable recency boost
        recency_weight: Weight for recency score (0-1), llm_weight will be 1 - recency_weight
        decay_rate: Exponential decay rate
        max_age_days: Maximum age for recency scoring
    """
    # Initialize config (required before using SiteConfigLookup)
    import os
    from pathlib import Path

    from nlweb_core.config import initialize_config

    # Set config directory and file if not specified
    script_dir = Path(__file__).parent

    if not os.getenv("NLWEB_CONFIG_DIR"):
        os.environ["NLWEB_CONFIG_DIR"] = str(script_dir)

    if not os.getenv("NLWEB_CONFIG_FILE"):
        # Use config-llm-scoring.yaml (has site_config enabled)
        os.environ["NLWEB_CONFIG_FILE"] = "config-llm-scoring.yaml"

    print(f"Config dir: {os.getenv('NLWEB_CONFIG_DIR')}")
    print(f"Config file: {os.getenv('NLWEB_CONFIG_FILE')}")

    initialize_config()

    # Import here to ensure env vars are loaded
    from nlweb_cosmos_site_config.site_config_lookup import SiteConfigLookup

    # Calculate LLM weight
    llm_weight = 1.0 - recency_weight

    print(f"\nAdding recency boost config for: {domain}")
    print(f"  Enabled: {enabled}")
    print(f"  Recency Weight: {recency_weight}")
    print(f"  LLM Weight: {llm_weight} (calculated as 1 - recency_weight)")
    print(f"  Decay Rate: {decay_rate}")
    print(f"  Max Age Days: {max_age_days}")

    # Validate recency_weight is in valid range
    if recency_weight < 0.0 or recency_weight > 1.0:
        print(
            f"\n⚠️  ERROR: recency_weight must be between 0 and 1 (got {recency_weight})"
        )
        print("Aborted.")
        return

    config = {
        "recency_boost": {
            "enabled": enabled,
            "recency_weight": recency_weight,
            "decay_rate": decay_rate,
            "max_age_days": max_age_days,
        }
    }

    try:
        lookup = SiteConfigLookup()

        # Check if config already exists
        existing = await lookup.get_config_type(domain, "freshness_config")
        if existing:
            print(f"\n⚠️  Existing freshness_config found:")
            print(f"  {existing}")
            response = input("\nOverwrite? [y/N]: ")
            if response.lower() != "y":
                print("Aborted.")
                await lookup.close()
                return

        # Update config
        result = await lookup.update_config_type(domain, "freshness_config", config)

        if result.get("created"):
            print(f"\n✅ New site config created for {domain}")
        else:
            print(f"\n✅ Site config updated for {domain}")

        print(f"   Config ID: {result.get('id')}")

        # Verify
        print("\n🔍 Verifying...")
        verified = await lookup.get_config_type(domain, "freshness_config")
        if verified and verified.get("recency_boost", {}).get("enabled"):
            print(f"✅ Recency boost confirmed active for {domain}")
        else:
            print(f"⚠️  Warning: Could not verify recency boost config")

        await lookup.close()

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Add recency boost configuration for a site"
    )
    parser.add_argument("domain", help="Domain name (e.g., aajtak.in)")
    parser.add_argument(
        "--enabled",
        action="store_true",
        default=True,
        help="Enable recency boost (default: True)",
    )
    parser.add_argument("--disabled", action="store_true", help="Disable recency boost")
    parser.add_argument(
        "--recency-weight",
        type=float,
        default=0.15,
        help="Weight for recency score, 0-1 (default: 0.15). LLM weight = 1 - recency_weight",
    )
    parser.add_argument(
        "--decay-rate",
        type=float,
        default=0.1,
        help="Exponential decay rate (default: 0.1)",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=90,
        help="Maximum age for recency scoring (default: 90)",
    )
    parser.add_argument(
        "--preset",
        choices=["news", "blog", "disable"],
        help="Use preset configuration (news, blog, or disable)",
    )

    args = parser.parse_args()

    # Apply presets
    if args.preset == "news":
        print("📰 Using NEWS preset (high recency weight, fast decay)")
        args.recency_weight = 0.15
        args.decay_rate = 0.1
        args.max_age_days = 90
        args.enabled = True
    elif args.preset == "blog":
        print("📝 Using BLOG preset (moderate recency weight, slow decay)")
        args.recency_weight = 0.10
        args.decay_rate = 0.05
        args.max_age_days = 180
        args.enabled = True
    elif args.preset == "disable":
        print("🚫 Disabling recency boost")
        args.enabled = False

    if args.disabled:
        args.enabled = False

    asyncio.run(
        add_recency_config(
            domain=args.domain,
            enabled=args.enabled,
            recency_weight=args.recency_weight,
            decay_rate=args.decay_rate,
            max_age_days=args.max_age_days,
        )
    )


if __name__ == "__main__":
    main()
