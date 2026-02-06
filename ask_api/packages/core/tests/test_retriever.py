"""
Tests for NLWeb retriever module.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nlweb_core.item_retriever import RetrievedItem
from nlweb_core.retriever import (
    ObjectLookupProvider,
    RetrievalProvider,
    enrich_results_from_object_storage,
)


class TestEnrichResultsFromObjectStorage:
    """Tests for enrich_results_from_object_storage function."""

    @pytest.fixture
    def mock_object_lookup_client(self):
        """Create a mock ObjectLookupProvider."""
        mock = AsyncMock(spec=ObjectLookupProvider)
        return mock

    @pytest.fixture
    def sample_results(self):
        """Sample search results for testing."""
        return [
            RetrievedItem(url="https://example.com/1", raw_schema_object='{"name": "Item 1"}', site="site1"),
            RetrievedItem(url="https://example.com/2", raw_schema_object='{"name": "Item 2"}', site="site1"),
        ]

    async def test_enriches_results_with_full_objects(
        self, mock_object_lookup_client, sample_results
    ):
        """Test enriches results with full objects from storage."""
        mock_object_lookup_client.get_by_id.side_effect = [
            {"name": "Full Item 1", "description": "Full description 1", "extra": "data1"},
            {"name": "Full Item 2", "description": "Full description 2", "extra": "data2"},
        ]

        result = await enrich_results_from_object_storage(
            sample_results, mock_object_lookup_client
        )

        assert len(result) == 2
        assert result[0].url == "https://example.com/1"
        assert result[0].schema_object[0]["name"] == "Full Item 1"
        assert result[0].schema_object[0]["description"] == "Full description 1"
        assert result[0].site == "site1"

        assert result[1].url == "https://example.com/2"
        assert result[1].schema_object[0]["name"] == "Full Item 2"
        assert result[1].site == "site1"

    async def test_keeps_original_when_object_not_found(
        self, mock_object_lookup_client, sample_results
    ):
        """Test keeps original result when get_by_id returns None."""
        mock_object_lookup_client.get_by_id.side_effect = [
            {"name": "Full Item 1"},
            None,  # Second item not found
        ]

        result = await enrich_results_from_object_storage(
            sample_results, mock_object_lookup_client
        )

        assert len(result) == 2
        assert result[0].schema_object[0]["name"] == "Full Item 1"
        # Second result unchanged - compare by URL and raw_schema_object since objects may differ
        assert result[1].url == sample_results[1].url
        assert result[1].raw_schema_object == sample_results[1].raw_schema_object

    async def test_handles_empty_results_list(self, mock_object_lookup_client):
        """Test handles empty results list gracefully."""
        result = await enrich_results_from_object_storage(
            [], mock_object_lookup_client
        )
        assert result == []
        mock_object_lookup_client.get_by_id.assert_not_called()

    async def test_processes_results_concurrently(self, mock_object_lookup_client):
        """Test that results are processed concurrently with semaphore."""
        many_results = [
            RetrievedItem(url=f"https://example.com/{i}", raw_schema_object=f'{{"name": "Item {i}"}}', site="site1")
            for i in range(25)
        ]

        async def slow_lookup(url):
            import asyncio
            await asyncio.sleep(0.01)
            return {"name": f"Full {url}"}

        mock_object_lookup_client.get_by_id.side_effect = slow_lookup

        result = await enrich_results_from_object_storage(
            many_results, mock_object_lookup_client
        )

        assert len(result) == 25
        assert mock_object_lookup_client.get_by_id.call_count == 25


class TestRetrievedItemSchemaObject:
    """Tests for RetrievedItem schema_object lazy parsing."""

    def test_parses_json_string_to_list(self):
        """Test parses JSON string containing a dict into list[dict]."""
        item = RetrievedItem(
            url="https://example.com/1",
            raw_schema_object='{"name": "Test Item", "type": "Product"}',
            site="site1",
        )
        assert item.schema_object == [{"name": "Test Item", "type": "Product"}]

    def test_parses_json_array_string_to_list(self):
        """Test parses JSON string containing an array into list[dict]."""
        item = RetrievedItem(
            url="https://example.com/1",
            raw_schema_object='[{"name": "Item 1"}, {"name": "Item 2"}]',
            site="site1",
        )
        assert item.schema_object == [{"name": "Item 1"}, {"name": "Item 2"}]

    def test_accepts_dict_and_wraps_in_list(self):
        """Test wraps a dict input into a list."""
        item = RetrievedItem(
            url="https://example.com/1",
            raw_schema_object={"name": "Test Item", "price": 100},
            site="site1",
        )
        assert item.schema_object == [{"name": "Test Item", "price": 100}]

    def test_accepts_list_of_dicts(self):
        """Test accepts list[dict] as-is."""
        input_list = [{"name": "Item 1"}, {"name": "Item 2"}]
        item = RetrievedItem(
            url="https://example.com/1",
            raw_schema_object=input_list,
            site="site1",
        )
        assert item.schema_object == input_list

    def test_raises_on_invalid_json_when_accessed(self):
        """Test raises ValueError for invalid JSON string when schema_object is accessed."""
        item = RetrievedItem(
            url="https://example.com/1",
            raw_schema_object="not valid json {",
            site="site1",
        )
        # No error on construction, error on access
        with pytest.raises(ValueError) as exc_info:
            _ = item.schema_object
        assert "not valid JSON" in str(exc_info.value)

    def test_raises_on_non_dict_in_list_when_accessed(self):
        """Test raises ValueError when list contains non-dict items on access."""
        item = RetrievedItem(
            url="https://example.com/1",
            raw_schema_object=[{"name": "Valid"}, "invalid string"],
            site="site1",
        )
        # No error on construction, error on access
        with pytest.raises(ValueError) as exc_info:
            _ = item.schema_object
        assert "must contain dicts" in str(exc_info.value)

    def test_raises_on_primitive_json_when_accessed(self):
        """Test raises ValueError for JSON that parses to primitive type on access."""
        item = RetrievedItem(
            url="https://example.com/1",
            raw_schema_object='"just a string"',
            site="site1",
        )
        # No error on construction, error on access
        with pytest.raises(ValueError) as exc_info:
            _ = item.schema_object
        assert "must be str, dict, or list[dict]" in str(exc_info.value)

    def test_raises_on_number_input_when_accessed(self):
        """Test raises ValueError for numeric input on access."""
        item = RetrievedItem(
            url="https://example.com/1",
            raw_schema_object=123,  # type: ignore[arg-type]
            site="site1",
        )
        # No error on construction, error on access
        with pytest.raises(ValueError) as exc_info:
            _ = item.schema_object
        assert "must be str, dict, or list[dict]" in str(exc_info.value)

    def test_empty_list_accepted(self):
        """Test accepts empty list."""
        item = RetrievedItem(
            url="https://example.com/1",
            raw_schema_object=[],
            site="site1",
        )
        assert item.schema_object == []

    def test_default_empty_list(self):
        """Test default value is empty list when not provided."""
        item = RetrievedItem(
            url="https://example.com/1",
            site="site1",
        )
        assert item.schema_object == []

    def test_caches_parsed_result(self):
        """Test that parsed result is cached after first access."""
        item = RetrievedItem(
            url="https://example.com/1",
            raw_schema_object='{"name": "Test Item"}',
            site="site1",
        )
        # First access parses
        result1 = item.schema_object
        # Second access returns cached value
        result2 = item.schema_object
        assert result1 is result2  # Same object (cached)
