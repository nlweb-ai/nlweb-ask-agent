# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Comprehensive unit tests for CosmosSiteConfigLookup.

Tests cover:
1. Pure function tests (generate_config_id, normalize_domain)
2. Read operations (get_config, get_config_type)
3. Write operations with round-trip verification
4. Delete operations
5. Caching behavior
6. Normalization integration - all URL/domain variants access same DB row
7. Edge cases
"""

import hashlib
import time as time_module

import pytest
from nlweb_cosmos_site_config.site_config_lookup import (
    CosmosSiteConfigLookup,
    generate_config_id,
    normalize_domain,
)

# =============================================================================
# Pure Function Tests
# =============================================================================


class TestGenerateConfigId:
    """Tests for generate_config_id pure function."""

    def test_generates_sha256_hash(self):
        """Output is a valid SHA-256 hex string (64 chars)."""
        result = generate_config_id("example.com")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic_for_same_input(self):
        """Same input always produces same output."""
        result1 = generate_config_id("yelp.com")
        result2 = generate_config_id("yelp.com")
        assert result1 == result2

    def test_lowercases_input(self):
        """Input is lowercased before hashing."""
        result1 = generate_config_id("YELP.COM")
        result2 = generate_config_id("yelp.com")
        assert result1 == result2

    def test_strips_whitespace(self):
        """Whitespace is stripped before hashing."""
        result1 = generate_config_id("  yelp.com  ")
        result2 = generate_config_id("yelp.com")
        assert result1 == result2

    def test_different_domains_produce_different_ids(self):
        """Different domains produce different IDs."""
        result1 = generate_config_id("yelp.com")
        result2 = generate_config_id("google.com")
        assert result1 != result2

    def test_matches_expected_hash(self):
        """Output matches known SHA-256."""
        expected = hashlib.sha256("yelp.com".encode()).hexdigest()
        result = generate_config_id("yelp.com")
        assert result == expected


class TestNormalizeDomain:
    """Tests for normalize_domain pure function."""

    def test_lowercases_domain(self):
        """Domain is lowercased."""
        assert normalize_domain("YELP.COM") == "yelp.com"
        assert normalize_domain("Yelp.Com") == "yelp.com"

    def test_strips_whitespace(self):
        """Whitespace is stripped."""
        assert normalize_domain("  yelp.com  ") == "yelp.com"
        assert normalize_domain("\tyelp.com\n") == "yelp.com"

    def test_removes_www_prefix(self):
        """www. prefix is removed."""
        assert normalize_domain("www.yelp.com") == "yelp.com"
        assert normalize_domain("WWW.yelp.com") == "yelp.com"
        assert normalize_domain("WWW.YELP.COM") == "yelp.com"

    def test_extracts_netloc_from_https_url(self):
        """Domain is extracted from HTTPS URL."""
        assert normalize_domain("https://yelp.com") == "yelp.com"
        assert normalize_domain("https://www.yelp.com") == "yelp.com"
        assert normalize_domain("https://yelp.com/some/path") == "yelp.com"
        assert normalize_domain("https://www.yelp.com/biz/pizza-place") == "yelp.com"

    def test_extracts_netloc_from_http_url(self):
        """Domain is extracted from HTTP URL."""
        assert normalize_domain("http://yelp.com") == "yelp.com"
        assert normalize_domain("http://www.yelp.com") == "yelp.com"

    def test_handles_url_with_port(self):
        """Port is included in normalized domain."""
        assert normalize_domain("https://yelp.com:8080") == "yelp.com:8080"

    def test_handles_url_with_query_string(self):
        """Query string is ignored."""
        assert normalize_domain("https://yelp.com/search?q=pizza") == "yelp.com"

    def test_handles_url_with_fragment(self):
        """Fragment is ignored."""
        assert normalize_domain("https://yelp.com/page#section") == "yelp.com"

    def test_preserves_subdomain_other_than_www(self):
        """Subdomains other than www are preserved."""
        assert normalize_domain("api.yelp.com") == "api.yelp.com"
        assert normalize_domain("https://api.yelp.com") == "api.yelp.com"

    def test_plain_domain_unchanged(self):
        """Plain domain (no www, no URL) is normalized."""
        assert normalize_domain("yelp.com") == "yelp.com"

    @pytest.mark.parametrize(
        "input_value",
        [
            "yelp.com",
            "Yelp.com",
            "YELP.COM",
            "www.yelp.com",
            "WWW.yelp.com",
            "WWW.YELP.COM",
            "https://yelp.com",
            "https://www.yelp.com",
            "https://YELP.COM",
            "https://WWW.YELP.COM",
            "https://yelp.com/some/path",
            "https://www.yelp.com/biz/pizza",
            "http://yelp.com",
            "http://www.yelp.com",
            "  yelp.com  ",
            "  https://www.yelp.com  ",
        ],
    )
    def test_all_yelp_variants_normalize_to_same_value(self, input_value):
        """All forms of yelp.com normalize to 'yelp.com'."""
        assert normalize_domain(input_value) == "yelp.com"


# =============================================================================
# Read Operation Tests
# =============================================================================


class TestGetConfig:
    """Tests for get_config read operation."""

    async def test_returns_none_for_nonexistent_site(self, site_config_lookup):
        """Returns None when site has no config."""
        result = await site_config_lookup.get_config("nonexistent.com")
        assert result is None

    async def test_returns_config_for_existing_site(
        self, site_config_lookup, fake_container
    ):
        """Returns config dict for site that exists."""
        normalized = "yelp.com"
        config_id = generate_config_id(normalized)
        await fake_container.upsert_item(
            {
                "id": config_id,
                "domain": normalized,
                "config": {"elicitation": {"prompt": "Test prompt"}},
            }
        )

        result = await site_config_lookup.get_config("yelp.com")

        assert result == {"elicitation": {"prompt": "Test prompt"}}

    async def test_normalizes_site_parameter(self, site_config_lookup, fake_container):
        """Site parameter is normalized before lookup."""
        normalized = "yelp.com"
        config_id = generate_config_id(normalized)
        await fake_container.upsert_item(
            {
                "id": config_id,
                "domain": normalized,
                "config": {"key": "value"},
            }
        )

        # All forms should find the same data
        assert await site_config_lookup.get_config("yelp.com") == {"key": "value"}

        # Clear cache to test with different forms
        site_config_lookup.cache.clear()
        assert await site_config_lookup.get_config("YELP.COM") == {"key": "value"}

        site_config_lookup.cache.clear()
        assert await site_config_lookup.get_config("www.yelp.com") == {"key": "value"}

        site_config_lookup.cache.clear()
        assert await site_config_lookup.get_config("https://yelp.com") == {
            "key": "value"
        }

        site_config_lookup.cache.clear()
        assert await site_config_lookup.get_config("https://www.yelp.com/path") == {
            "key": "value"
        }


class TestGetConfigType:
    """Tests for get_config_type read operation."""

    async def test_returns_none_for_nonexistent_site(self, site_config_lookup):
        """Returns None when site has no config."""
        result = await site_config_lookup.get_config_type(
            "nonexistent.com", "elicitation"
        )
        assert result is None

    async def test_returns_none_for_nonexistent_config_type(
        self, site_config_lookup, fake_container
    ):
        """Returns None when config type doesn't exist."""
        normalized = "yelp.com"
        config_id = generate_config_id(normalized)
        await fake_container.upsert_item(
            {
                "id": config_id,
                "domain": normalized,
                "config": {"elicitation": {"prompt": "Test"}},
            }
        )

        result = await site_config_lookup.get_config_type("yelp.com", "scoring_specs")
        assert result is None

    async def test_returns_specific_config_type(
        self, site_config_lookup, fake_container
    ):
        """Returns specific config type when it exists."""
        normalized = "yelp.com"
        config_id = generate_config_id(normalized)
        await fake_container.upsert_item(
            {
                "id": config_id,
                "domain": normalized,
                "config": {
                    "elicitation": {"prompt": "Elicitation prompt"},
                    "scoring_specs": {"threshold": 0.5},
                },
            }
        )

        result = await site_config_lookup.get_config_type("yelp.com", "elicitation")
        assert result == {"prompt": "Elicitation prompt"}

        site_config_lookup.cache.clear()
        result = await site_config_lookup.get_config_type("yelp.com", "scoring_specs")
        assert result == {"threshold": 0.5}


# =============================================================================
# Write Operation Tests (Round-trip Focus)
# =============================================================================


class TestUpdateConfigType:
    """Tests for update_config_type write operation with round-trip verification."""

    async def test_creates_new_config_for_new_site(self, site_config_lookup):
        """Creating config for a site that doesn't exist."""
        config_data = {"prompt": "What are you looking for?", "max_turns": 3}

        result = await site_config_lookup.update_config_type(
            "yelp.com", "elicitation", config_data
        )

        assert result["created"] is True
        assert "id" in result

        # Round-trip verification: read back exactly what we wrote
        read_back = await site_config_lookup.get_config_type("yelp.com", "elicitation")
        assert read_back == config_data

    async def test_updates_existing_config_type(self, site_config_lookup):
        """Updating an existing config type."""
        # Create initial config
        initial_data = {"prompt": "Initial prompt"}
        await site_config_lookup.update_config_type(
            "yelp.com", "elicitation", initial_data
        )

        # Update the config
        updated_data = {"prompt": "Updated prompt", "new_field": True}
        result = await site_config_lookup.update_config_type(
            "yelp.com", "elicitation", updated_data
        )

        assert result["created"] is False

        # Round-trip: verify the update
        read_back = await site_config_lookup.get_config_type("yelp.com", "elicitation")
        assert read_back == updated_data
        assert read_back != initial_data

    async def test_adds_new_config_type_to_existing_site(self, site_config_lookup):
        """Adding a new config type to a site that already has config."""
        # Create initial config type
        await site_config_lookup.update_config_type(
            "yelp.com", "elicitation", {"prompt": "Test"}
        )

        # Add a different config type
        scoring_data = {"threshold": 0.7, "boost_factor": 1.5}
        result = await site_config_lookup.update_config_type(
            "yelp.com", "scoring_specs", scoring_data
        )

        assert result["created"] is False  # Site existed

        # Verify both config types exist
        elicitation = await site_config_lookup.get_config_type(
            "yelp.com", "elicitation"
        )
        scoring = await site_config_lookup.get_config_type("yelp.com", "scoring_specs")

        assert elicitation == {"prompt": "Test"}
        assert scoring == scoring_data

    async def test_write_via_url_read_via_domain(self, site_config_lookup):
        """Writing via URL and reading via domain returns same data."""
        config_data = {"key": "value", "nested": {"a": 1}}

        # Write using full URL
        await site_config_lookup.update_config_type(
            "https://www.yelp.com/biz/something", "test_config", config_data
        )

        # Read using plain domain
        result = await site_config_lookup.get_config_type("yelp.com", "test_config")
        assert result == config_data

    async def test_write_via_domain_read_via_url(self, site_config_lookup):
        """Writing via domain and reading via URL returns same data."""
        config_data = {"complex": [1, 2, 3], "nested": {"deep": {"value": True}}}

        # Write using plain domain
        await site_config_lookup.update_config_type(
            "yelp.com", "test_config", config_data
        )

        # Read using various URL forms (clear cache between reads)
        site_config_lookup.cache.clear()
        result1 = await site_config_lookup.get_config_type(
            "https://www.yelp.com", "test_config"
        )
        assert result1 == config_data

        site_config_lookup.cache.clear()
        result2 = await site_config_lookup.get_config_type(
            "https://yelp.com/path?query=1", "test_config"
        )
        assert result2 == config_data

        site_config_lookup.cache.clear()
        result3 = await site_config_lookup.get_config_type(
            "WWW.YELP.COM", "test_config"
        )
        assert result3 == config_data

    async def test_preserves_complex_nested_structures(self, site_config_lookup):
        """Complex nested data structures survive round-trip."""
        complex_config = {
            "string": "value",
            "number": 42,
            "float": 3.14159,
            "boolean": True,
            "null": None,
            "list": [1, "two", 3.0, None, {"nested": True}],
            "nested": {"level1": {"level2": {"level3": ["deep", "values"]}}},
            "empty_list": [],
            "empty_dict": {},
        }

        await site_config_lookup.update_config_type(
            "yelp.com", "complex", complex_config
        )

        result = await site_config_lookup.get_config_type("yelp.com", "complex")
        assert result == complex_config


class TestRoundTripIntegrity:
    """
    Dedicated tests for round-trip data integrity.
    Ensures that what goes in comes out exactly the same.
    """

    @pytest.mark.parametrize(
        "config_data",
        [
            {"simple": "string"},
            {"number": 42},
            {"float": 3.14159265358979},
            {"boolean_true": True, "boolean_false": False},
            {"null_value": None},
            {"empty_string": ""},
            {"unicode": "Hello \u4e16\u754c \U0001f600"},
            {"special_chars": "line1\nline2\ttab"},
            {"list_of_dicts": [{"a": 1}, {"b": 2}]},
            {"deeply_nested": {"l1": {"l2": {"l3": {"l4": "value"}}}}},
        ],
    )
    async def test_config_data_survives_roundtrip(
        self, site_config_lookup, config_data
    ):
        """Various data types survive round-trip exactly."""
        await site_config_lookup.update_config_type("test.com", "config", config_data)

        result = await site_config_lookup.get_config_type("test.com", "config")
        assert result == config_data


# =============================================================================
# Delete Operation Tests
# =============================================================================


class TestDeleteConfigType:
    """Tests for delete_config_type operation."""

    async def test_returns_none_for_nonexistent_site(self, site_config_lookup):
        """Returns None when deleting from nonexistent site."""
        result = await site_config_lookup.delete_config_type(
            "nonexistent.com", "elicitation"
        )
        assert result is None

    async def test_returns_none_for_nonexistent_config_type(self, site_config_lookup):
        """Returns None when config type doesn't exist."""
        await site_config_lookup.update_config_type(
            "yelp.com", "elicitation", {"prompt": "Test"}
        )

        result = await site_config_lookup.delete_config_type(
            "yelp.com", "scoring_specs"
        )
        assert result is None

    async def test_deletes_specific_config_type(self, site_config_lookup):
        """Deleting a specific config type preserves others."""
        # Create multiple config types
        await site_config_lookup.update_config_type(
            "yelp.com", "elicitation", {"prompt": "Test"}
        )
        await site_config_lookup.update_config_type(
            "yelp.com", "scoring_specs", {"threshold": 0.5}
        )

        # Delete one
        result = await site_config_lookup.delete_config_type("yelp.com", "elicitation")
        assert result == {"deleted": True, "domain_deleted": False}

        # Verify deleted type is gone
        assert (
            await site_config_lookup.get_config_type("yelp.com", "elicitation") is None
        )

        # Verify other type still exists
        assert await site_config_lookup.get_config_type(
            "yelp.com", "scoring_specs"
        ) == {"threshold": 0.5}

    async def test_deletes_entire_document_when_last_config_type(
        self, site_config_lookup
    ):
        """Document is deleted when last config type is removed."""
        # Create single config type
        await site_config_lookup.update_config_type(
            "yelp.com", "elicitation", {"prompt": "Test"}
        )

        # Delete it
        result = await site_config_lookup.delete_config_type("yelp.com", "elicitation")
        assert result == {"deleted": True, "domain_deleted": True}

        # Verify site has no config
        assert await site_config_lookup.get_config("yelp.com") is None


class TestDeleteFullConfig:
    """Tests for delete_full_config operation."""

    async def test_returns_false_for_nonexistent_site(self, site_config_lookup):
        """Returns False when site doesn't exist."""
        result = await site_config_lookup.delete_full_config("nonexistent.com")
        assert result is False

    async def test_deletes_all_config_types(self, site_config_lookup):
        """Deletes entire document with all config types."""
        # Create multiple config types
        await site_config_lookup.update_config_type(
            "yelp.com", "elicitation", {"prompt": "Test"}
        )
        await site_config_lookup.update_config_type(
            "yelp.com", "scoring_specs", {"threshold": 0.5}
        )
        await site_config_lookup.update_config_type(
            "yelp.com", "item_types", ["Restaurant", "LocalBusiness"]
        )

        # Delete all
        result = await site_config_lookup.delete_full_config("yelp.com")
        assert result is True

        # Verify all gone
        assert await site_config_lookup.get_config("yelp.com") is None

    async def test_normalizes_site_parameter(self, site_config_lookup):
        """Site is normalized for delete operation."""
        await site_config_lookup.update_config_type(
            "yelp.com", "config", {"key": "value"}
        )

        # Delete using URL form
        result = await site_config_lookup.delete_full_config(
            "https://www.yelp.com/path"
        )
        assert result is True

        # Verify deleted
        assert await site_config_lookup.get_config("yelp.com") is None


# =============================================================================
# Caching Tests
# =============================================================================


class TestCaching:
    """Tests for caching behavior."""

    async def test_cache_is_populated_on_read(self, site_config_lookup, fake_container):
        """Cache is populated after read."""
        normalized = "yelp.com"
        config_id = generate_config_id(normalized)
        await fake_container.upsert_item(
            {
                "id": config_id,
                "domain": normalized,
                "config": {"key": "value"},
            }
        )

        # First read populates cache
        await site_config_lookup.get_config("yelp.com")

        assert normalized in site_config_lookup.cache
        assert site_config_lookup.cache[normalized]["config"] == {"key": "value"}

    async def test_cache_is_used_on_subsequent_reads(
        self, site_config_lookup, fake_container
    ):
        """Cached value is returned without hitting container."""
        normalized = "yelp.com"
        config_id = generate_config_id(normalized)
        await fake_container.upsert_item(
            {
                "id": config_id,
                "domain": normalized,
                "config": {"key": "original"},
            }
        )
        await site_config_lookup.get_config("yelp.com")

        # Modify container directly (simulating external change)
        await fake_container.upsert_item(
            {
                "id": config_id,
                "domain": normalized,
                "config": {"key": "modified"},
            }
        )

        # Should still return cached value
        result = await site_config_lookup.get_config("yelp.com")
        assert result == {"key": "original"}

    async def test_cache_is_invalidated_on_write(self, site_config_lookup):
        """Cache is invalidated after write."""
        # Create initial config
        await site_config_lookup.update_config_type("yelp.com", "config", {"key": "v1"})

        # Read to ensure cache is populated
        await site_config_lookup.get_config("yelp.com")
        assert "yelp.com" in site_config_lookup.cache

        # Write new value
        await site_config_lookup.update_config_type("yelp.com", "config", {"key": "v2"})

        # Cache should be invalidated
        assert "yelp.com" not in site_config_lookup.cache

    async def test_cache_is_invalidated_on_delete(self, site_config_lookup):
        """Cache is invalidated after delete."""
        # Create config
        await site_config_lookup.update_config_type(
            "yelp.com", "config", {"key": "value"}
        )

        # Read to populate cache
        await site_config_lookup.get_config("yelp.com")
        assert "yelp.com" in site_config_lookup.cache

        # Delete
        await site_config_lookup.delete_full_config("yelp.com")

        # Cache should be invalidated
        assert "yelp.com" not in site_config_lookup.cache

    async def test_cache_ttl_expiration(
        self, site_config_lookup, fake_container, monkeypatch
    ):
        """Cache entries expire after TTL."""
        normalized = "yelp.com"
        config_id = generate_config_id(normalized)
        await fake_container.upsert_item(
            {
                "id": config_id,
                "domain": normalized,
                "config": {"key": "original"},
            }
        )
        await site_config_lookup.get_config("yelp.com")

        # Modify container
        await fake_container.upsert_item(
            {
                "id": config_id,
                "domain": normalized,
                "config": {"key": "modified"},
            }
        )

        # Mock time to simulate TTL expiration
        original_time = time_module.time()
        monkeypatch.setattr(
            time_module,
            "time",
            lambda: original_time + site_config_lookup.cache_ttl + 1,
        )

        # Should fetch fresh value due to expired cache
        result = await site_config_lookup.get_config("yelp.com")
        assert result == {"key": "modified"}

    async def test_cache_invalidation_normalizes_site(self, site_config_lookup):
        """Cache invalidation works with normalized domain."""
        # Create with one form
        await site_config_lookup.update_config_type(
            "https://www.yelp.com", "config", {"key": "value"}
        )

        # Read with different form to populate cache
        await site_config_lookup.get_config("yelp.com")
        assert "yelp.com" in site_config_lookup.cache

        # Update with yet another form
        await site_config_lookup.update_config_type(
            "WWW.YELP.COM", "config", {"key": "updated"}
        )

        # Cache should be invalidated for normalized domain
        assert "yelp.com" not in site_config_lookup.cache

        # Next read should get updated value
        result = await site_config_lookup.get_config("YELP.COM")
        assert result == {"config": {"key": "updated"}}

    async def test_caches_none_for_missing_site(self, site_config_lookup):
        """None is cached for missing sites to avoid repeated lookups."""
        await site_config_lookup.get_config("missing.com")

        assert "missing.com" in site_config_lookup.cache
        assert site_config_lookup.cache["missing.com"]["config"] is None


# =============================================================================
# Normalization Integration Tests
# =============================================================================


class TestNormalizationIntegration:
    """
    Integration tests ensuring different URL/domain forms access the same DB row.
    This is critical: All variants should work with the same data.
    """

    YELP_VARIANTS = [
        "yelp.com",
        "Yelp.com",
        "YELP.COM",
        "www.yelp.com",
        "WWW.yelp.com",
        "WWW.YELP.COM",
        "https://yelp.com",
        "https://www.yelp.com",
        "https://YELP.COM",
        "https://WWW.YELP.COM",
        "https://yelp.com/some/path",
        "https://www.yelp.com/biz/pizza-place",
        "http://yelp.com",
        "http://www.yelp.com",
        "  yelp.com  ",
        "  https://www.yelp.com  ",
    ]

    async def test_all_variants_access_same_row_for_reads(
        self, site_config_lookup, fake_container
    ):
        """All domain variants read from the same DB row."""
        normalized = "yelp.com"
        config_id = generate_config_id(normalized)
        await fake_container.upsert_item(
            {
                "id": config_id,
                "domain": normalized,
                "config": {"shared": "data"},
            }
        )

        # All variants should read the same data
        for variant in self.YELP_VARIANTS:
            site_config_lookup.cache.clear()  # Clear cache to force DB read
            result = await site_config_lookup.get_config(variant)
            assert result == {"shared": "data"}, f"Failed for variant: {variant}"

    async def test_write_from_any_variant_affects_all_reads(self, site_config_lookup):
        """Writing from any variant is readable from all others."""
        # Write using URL form
        await site_config_lookup.update_config_type(
            "https://www.yelp.com/biz/test", "config", {"written_via": "url"}
        )

        # All variants should see the data
        for variant in self.YELP_VARIANTS:
            site_config_lookup.cache.clear()  # Clear cache to force DB read
            result = await site_config_lookup.get_config_type(variant, "config")
            assert result == {"written_via": "url"}, f"Failed for variant: {variant}"

    async def test_only_one_document_created_for_all_variants(
        self, site_config_lookup, fake_container
    ):
        """Writing via multiple variants creates only one document."""
        # Write using different variants
        await site_config_lookup.update_config_type("yelp.com", "type1", {"v": 1})
        await site_config_lookup.update_config_type("WWW.YELP.COM", "type2", {"v": 2})
        await site_config_lookup.update_config_type(
            "https://www.yelp.com/path", "type3", {"v": 3}
        )

        # Should only have one document in container
        all_docs = fake_container.get_all_documents()
        assert len(all_docs) == 1

        # That document should have all three config types
        doc = all_docs[0]
        assert doc["domain"] == "yelp.com"
        assert doc["config"]["type1"] == {"v": 1}
        assert doc["config"]["type2"] == {"v": 2}
        assert doc["config"]["type3"] == {"v": 3}

    async def test_delete_from_any_variant_affects_all(self, site_config_lookup):
        """Deleting from any variant removes data for all."""
        # Create config
        await site_config_lookup.update_config_type(
            "yelp.com", "config", {"data": "value"}
        )

        # Delete using different variant
        await site_config_lookup.delete_full_config("https://WWW.YELP.COM/path?query=1")

        # All variants should see no data
        for variant in self.YELP_VARIANTS:
            site_config_lookup.cache.clear()
            result = await site_config_lookup.get_config(variant)
            assert result is None, f"Data still exists for variant: {variant}"


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling scenarios."""

    async def test_handles_cosmos_not_found_gracefully(self, site_config_lookup):
        """CosmosResourceNotFoundError is handled gracefully."""
        result = await site_config_lookup.get_config("nonexistent.com")
        assert result is None

    def test_init_rejects_unexpected_kwargs(self):
        """__init__ rejects unexpected keyword arguments."""
        with pytest.raises(TypeError) as exc_info:
            CosmosSiteConfigLookup(
                endpoint="https://test.cosmos.azure.com",
                database_name="db",
                container_name="container",
                cache_ttl=60,
                unexpected_arg="value",
            )

        assert "unexpected arguments" in str(exc_info.value)
        assert "unexpected_arg" in str(exc_info.value)


class TestClientLifecycle:
    """Tests for client initialization and cleanup."""

    async def test_client_initialized_lazily(self, site_config_lookup):
        """Cosmos client is not created until first use."""
        assert site_config_lookup._client is None

        await site_config_lookup.get_config("test.com")

        assert site_config_lookup._client is not None

    async def test_close_cleans_up_resources(self, site_config_lookup):
        """close() properly cleans up resources."""
        await site_config_lookup.get_config("test.com")
        assert site_config_lookup._client is not None

        await site_config_lookup.close()

        assert site_config_lookup._client is None
        assert site_config_lookup._container is None

    async def test_close_is_idempotent(self, site_config_lookup):
        """close() can be called multiple times safely."""
        await site_config_lookup.close()
        await site_config_lookup.close()  # Should not raise


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    async def test_empty_config_dict(self, site_config_lookup):
        """Handling of empty config dict."""
        await site_config_lookup.update_config_type("test.com", "config", {})

        result = await site_config_lookup.get_config_type("test.com", "config")
        assert result == {}

    async def test_config_with_empty_string_value(self, site_config_lookup):
        """Config with empty string value."""
        await site_config_lookup.update_config_type("test.com", "config", {"key": ""})

        result = await site_config_lookup.get_config_type("test.com", "config")
        assert result == {"key": ""}

    async def test_multiple_sites_isolation(self, site_config_lookup):
        """Different sites are properly isolated."""
        await site_config_lookup.update_config_type(
            "site1.com", "config", {"site": "one"}
        )
        await site_config_lookup.update_config_type(
            "site2.com", "config", {"site": "two"}
        )

        assert await site_config_lookup.get_config_type("site1.com", "config") == {
            "site": "one"
        }
        assert await site_config_lookup.get_config_type("site2.com", "config") == {
            "site": "two"
        }

    async def test_domain_with_subdomain(self, site_config_lookup):
        """Subdomains are treated as separate sites."""
        await site_config_lookup.update_config_type(
            "api.yelp.com", "config", {"is_api": True}
        )
        await site_config_lookup.update_config_type(
            "yelp.com", "config", {"is_main": True}
        )

        assert await site_config_lookup.get_config_type("api.yelp.com", "config") == {
            "is_api": True
        }
        assert await site_config_lookup.get_config_type("yelp.com", "config") == {
            "is_main": True
        }

    async def test_very_long_domain(self, site_config_lookup):
        """Handling of very long domain names."""
        long_domain = "a" * 100 + ".example.com"

        await site_config_lookup.update_config_type(
            long_domain, "config", {"long": True}
        )

        result = await site_config_lookup.get_config_type(long_domain, "config")
        assert result == {"long": True}

    async def test_special_characters_in_config_type(self, site_config_lookup):
        """Config type names with special characters."""
        config_types = [
            "type_with_underscore",
            "type-with-dash",
            "type.with.dots",
            "TypeWithCamelCase",
        ]

        for config_type in config_types:
            await site_config_lookup.update_config_type(
                "test.com", config_type, {"type": config_type}
            )
            result = await site_config_lookup.get_config_type("test.com", config_type)
            assert result == {"type": config_type}

    async def test_config_with_list_value(self, site_config_lookup):
        """Config type can be a list (not just dict)."""
        await site_config_lookup.update_config_type(
            "test.com", "item_types", ["Restaurant", "LocalBusiness"]
        )

        result = await site_config_lookup.get_config_type("test.com", "item_types")
        assert result == ["Restaurant", "LocalBusiness"]
