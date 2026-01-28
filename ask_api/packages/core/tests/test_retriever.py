"""
Tests for NLWeb retriever module.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nlweb_core.config import ObjectLookupConfig, RetrievalProviderConfig
from nlweb_core.item_retriever import RetrievedItem
from nlweb_core.retriever import (
    ObjectLookupInterface,
    VectorDBClientInterface,
    _has_valid_credentials,
    _resolve_endpoint_name,
    enrich_results_from_object_storage,
    get_object_lookup_client,
    get_vectordb_client,
)


def reset_retriever_caches():
    """Reset all module-level caches for clean test state."""
    import nlweb_core.retriever as retriever

    retriever._client_cache.clear()
    retriever._object_lookup_client = None


class TestHasValidCredentials:
    """Tests for _has_valid_credentials function."""

    def test_returns_true_for_database_path(self):
        """Test returns True when database_path is set."""
        config = RetrievalProviderConfig(database_path="/path/to/db")
        assert _has_valid_credentials(config) is True

    def test_returns_true_for_api_endpoint(self):
        """Test returns True when api_endpoint is set."""
        config = RetrievalProviderConfig(api_endpoint="https://api.example.com")
        assert _has_valid_credentials(config) is True

    def test_returns_true_for_import_path(self):
        """Test returns True when import_path is set."""
        config = RetrievalProviderConfig(import_path="some.module")
        assert _has_valid_credentials(config) is True

    def test_returns_false_when_nothing_set(self):
        """Test returns False when no credentials are configured."""
        config = RetrievalProviderConfig()
        assert _has_valid_credentials(config) is False

    def test_returns_false_for_empty_strings(self):
        """Test returns False when credentials are empty strings."""
        config = RetrievalProviderConfig(database_path="", api_endpoint="", import_path="")
        assert _has_valid_credentials(config) is False


class TestResolveEndpointName:
    """Tests for _resolve_endpoint_name function."""

    @pytest.fixture(autouse=True)
    def setup_config_mock(self):
        """Setup get_config mock for all tests in this class."""
        self.mock_config = MagicMock()
        with patch("nlweb_core.retriever.get_config", return_value=self.mock_config):
            yield self.mock_config

    def test_selects_first_enabled_endpoint(self):
        """Test auto-selects first enabled endpoint with valid credentials."""
        self.mock_config.retrieval_endpoints = {
            "endpoint1": RetrievalProviderConfig(enabled=False),
            "endpoint2": RetrievalProviderConfig(
                enabled=True, api_endpoint="https://api.example.com"
            ),
            "endpoint3": RetrievalProviderConfig(
                enabled=True, database_path="/path/to/db"
            ),
        }

        result = _resolve_endpoint_name()
        assert result == "endpoint2"

    def test_raises_when_no_enabled_endpoints(self):
        """Test raises ValueError when no endpoints are enabled."""
        self.mock_config.retrieval_endpoints = {
            "endpoint1": RetrievalProviderConfig(enabled=False, database_path="/path"),
        }

        with pytest.raises(ValueError) as exc_info:
            _resolve_endpoint_name()
        assert "no enabled endpoints" in str(exc_info.value).lower()


class TestEnrichResultsFromObjectStorage:
    """Tests for enrich_results_from_object_storage function."""

    @pytest.fixture
    def mock_object_lookup_client(self):
        """Create a mock ObjectLookupInterface."""
        mock = AsyncMock(spec=ObjectLookupInterface)
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


class TestGetObjectLookupClient:
    """Tests for get_object_lookup_client function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset caches before each test."""
        reset_retriever_caches()
        yield
        reset_retriever_caches()

    async def test_returns_none_when_disabled(self):
        """Test returns None when object_storage is disabled."""
        with patch("nlweb_core.retriever.get_config") as mock_get_config:
            mock_get_config.return_value.object_storage = ObjectLookupConfig(type="cosmos", enabled=False)

            result = await get_object_lookup_client()
            assert result is None

    async def test_returns_none_when_object_storage_not_configured(self):
        """Test returns None when object_storage config is None."""
        with patch("nlweb_core.retriever.get_config") as mock_get_config:
            mock_get_config.return_value.object_storage = None

            result = await get_object_lookup_client()
            assert result is None

    async def test_raises_when_missing_import_path(self):
        """Test raises ValueError when import_path is missing."""
        with patch("nlweb_core.retriever.get_config") as mock_get_config:
            mock_get_config.return_value.object_storage = ObjectLookupConfig(
                type="cosmos",
                enabled=True,
                class_name="SomeClass",
            )

            with pytest.raises(ValueError) as exc_info:
                await get_object_lookup_client()
            assert "missing import_path or class_name" in str(exc_info.value)

    async def test_raises_when_missing_class_name(self):
        """Test raises ValueError when class_name is missing."""
        with patch("nlweb_core.retriever.get_config") as mock_get_config:
            mock_get_config.return_value.object_storage = ObjectLookupConfig(
                type="cosmos",
                enabled=True,
                import_path="some.module",
            )

            with pytest.raises(ValueError) as exc_info:
                await get_object_lookup_client()
            assert "missing import_path or class_name" in str(exc_info.value)

    async def test_caches_client_instance(self):
        """Test that client is cached and reused."""
        mock_client_class = MagicMock()
        mock_client_instance = MagicMock(spec=ObjectLookupInterface)
        mock_client_class.return_value = mock_client_instance

        with patch("nlweb_core.retriever.get_config") as mock_get_config:
            mock_get_config.return_value.object_storage = ObjectLookupConfig(
                type="test",
                enabled=True,
                import_path="test_module",
                class_name="TestClient",
            )

            mock_module = MagicMock()
            mock_module.TestClient = mock_client_class

            with patch("nlweb_core.retriever.importlib.import_module", return_value=mock_module):
                client1 = await get_object_lookup_client()
                client2 = await get_object_lookup_client()

                assert client1 is client2
                mock_client_class.assert_called_once()

    async def test_raises_on_import_error(self):
        """Test raises ValueError when import fails."""
        with patch("nlweb_core.retriever.get_config") as mock_get_config:
            mock_get_config.return_value.object_storage = ObjectLookupConfig(
                type="test",
                enabled=True,
                import_path="nonexistent.module",
                class_name="NonexistentClass",
            )

            with pytest.raises(ValueError) as exc_info:
                await get_object_lookup_client()
            assert "Failed to load object storage client" in str(exc_info.value)


class TestGetVectordbClient:
    """Tests for get_vectordb_client function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset caches before each test."""
        reset_retriever_caches()
        yield
        reset_retriever_caches()

    async def test_resolves_endpoint_and_creates_client(self):
        """Test resolves endpoint name and creates appropriate client."""
        mock_client_class = MagicMock()
        mock_client_instance = MagicMock(spec=VectorDBClientInterface)
        mock_client_class.return_value = mock_client_instance

        with patch("nlweb_core.retriever.get_config") as mock_get_config:
            mock_config = mock_get_config.return_value
            endpoint_config = RetrievalProviderConfig(
                enabled=True,
                db_type="test_db",
                api_endpoint="https://api.example.com",
                import_path="test_provider",
                class_name="TestVectorClient",
            )
            mock_config.retrieval_endpoints = {"test_endpoint": endpoint_config}

            mock_module = MagicMock()
            mock_module.TestVectorClient = mock_client_class

            with patch("nlweb_core.retriever.importlib.import_module", return_value=mock_module):
                client = await get_vectordb_client()

                assert client is mock_client_instance
                mock_client_class.assert_called_once_with(endpoint_config)

    async def test_caches_client_by_endpoint(self):
        """Test that clients are cached by db_type and endpoint name."""
        mock_client_class = MagicMock()
        mock_client_instance = MagicMock(spec=VectorDBClientInterface)
        mock_client_class.return_value = mock_client_instance

        with patch("nlweb_core.retriever.get_config") as mock_get_config:
            mock_config = mock_get_config.return_value
            endpoint_config = RetrievalProviderConfig(
                enabled=True,
                db_type="test_db",
                database_path="/path",
                import_path="test_provider",
                class_name="TestVectorClient",
            )
            mock_config.retrieval_endpoints = {"test_endpoint": endpoint_config}

            mock_module = MagicMock()
            mock_module.TestVectorClient = mock_client_class

            with patch("nlweb_core.retriever.importlib.import_module", return_value=mock_module):
                client1 = await get_vectordb_client()
                client2 = await get_vectordb_client()

                assert client1 is client2
                mock_client_class.assert_called_once()

    async def test_raises_on_import_error(self):
        """Test raises ValueError when client import fails."""
        with patch("nlweb_core.retriever.get_config") as mock_get_config:
            mock_config = mock_get_config.return_value
            endpoint_config = RetrievalProviderConfig(
                enabled=True,
                db_type="bad_db",
                database_path="/path",
                import_path="nonexistent.module",
                class_name="NonexistentClass",
            )
            mock_config.retrieval_endpoints = {"bad_endpoint": endpoint_config}

            with pytest.raises(ValueError) as exc_info:
                await get_vectordb_client()
            assert "Failed to load client" in str(exc_info.value)

    async def test_raises_when_no_import_config(self):
        """Test raises ValueError when no import_path configured."""
        with patch("nlweb_core.retriever.get_config") as mock_get_config:
            mock_config = mock_get_config.return_value
            endpoint_config = RetrievalProviderConfig(
                enabled=True,
                db_type="unconfigured_db",
                database_path="/path",
            )
            mock_config.retrieval_endpoints = {"no_import_endpoint": endpoint_config}

            with pytest.raises(ValueError) as exc_info:
                await get_vectordb_client()
            assert "No import_path and class_name configured" in str(exc_info.value)

    async def test_uses_preloaded_module_when_available(self):
        """Test uses preloaded module from cache when available."""
        import nlweb_core.retriever as retriever

        mock_client_class = MagicMock()
        mock_client_instance = MagicMock(spec=VectorDBClientInterface)
        mock_client_class.return_value = mock_client_instance

        # Add to preloaded modules
        retriever._preloaded_modules["preloaded_db"] = mock_client_class

        try:
            with patch("nlweb_core.retriever.get_config") as mock_get_config:
                mock_config = mock_get_config.return_value
                endpoint_config = RetrievalProviderConfig(
                    enabled=True,
                    db_type="preloaded_db",
                    database_path="/path",
                    import_path="should.not.be.used",
                    class_name="ShouldNotBeUsed",
                )
                mock_config.retrieval_endpoints = {"preloaded_endpoint": endpoint_config}

                client = await get_vectordb_client()

                assert client is mock_client_instance
                mock_client_class.assert_called_once_with(endpoint_config)
        finally:
            # Clean up
            retriever._preloaded_modules.pop("preloaded_db", None)

    async def test_auto_selects_first_enabled_endpoint(self):
        """Test auto-selects first enabled endpoint when none specified."""
        mock_client_class = MagicMock()
        mock_client_instance = MagicMock(spec=VectorDBClientInterface)
        mock_client_class.return_value = mock_client_instance

        with patch("nlweb_core.retriever.get_config") as mock_get_config:
            mock_config = mock_get_config.return_value
            disabled_config = RetrievalProviderConfig(
                enabled=False,
                db_type="disabled_db",
                database_path="/path",
                import_path="disabled.module",
                class_name="DisabledClient",
            )
            enabled_config = RetrievalProviderConfig(
                enabled=True,
                db_type="enabled_db",
                database_path="/path",
                import_path="enabled.module",
                class_name="EnabledClient",
            )
            mock_config.retrieval_endpoints = {
                "disabled_endpoint": disabled_config,
                "enabled_endpoint": enabled_config,
            }

            mock_module = MagicMock()
            mock_module.EnabledClient = mock_client_class

            with patch("nlweb_core.retriever.importlib.import_module", return_value=mock_module):
                client = await get_vectordb_client()

                assert client is mock_client_instance
                mock_client_class.assert_called_once_with(enabled_config)


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
