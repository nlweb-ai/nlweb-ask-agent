# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Test fixtures for CosmosSiteConfigLookup.

Provides FakeCosmosContainer - an in-memory test double for Azure Cosmos DB container.
"""

from typing import Any

import pytest
from azure.cosmos import exceptions


class FakeCosmosContainer:
    """
    In-memory test double for Azure Cosmos DB container.

    Implements the same async interface as the real container:
    - read_item(item, partition_key) -> dict
    - upsert_item(body) -> dict
    - delete_item(item, partition_key) -> None

    Raises CosmosResourceNotFoundError when item not found.
    """

    def __init__(self):
        # Storage: {partition_key: {id: document}}
        self._data: dict[str, dict[str, dict[str, Any]]] = {}

    async def read_item(self, item: str, partition_key: str) -> dict[str, Any]:
        """
        Read item by id and partition key.

        Args:
            item: The document id
            partition_key: The partition key value

        Returns:
            The document dict

        Raises:
            CosmosResourceNotFoundError: If document not found
        """
        partition = self._data.get(partition_key, {})
        document = partition.get(item)

        if document is None:
            raise exceptions.CosmosResourceNotFoundError(
                status_code=404,
                message=f"Document with id '{item}' not found",
            )

        # Return a copy to prevent mutation
        return dict(document)

    async def upsert_item(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        Insert or update a document.

        The document must contain 'id' and the partition key field ('domain').

        Args:
            body: The document to upsert

        Returns:
            The upserted document
        """
        doc_id = body["id"]
        partition_key = body["domain"]  # Based on site_config_lookup.py schema

        if partition_key not in self._data:
            self._data[partition_key] = {}

        # Store a copy to prevent external mutation
        self._data[partition_key][doc_id] = dict(body)

        return dict(body)

    async def delete_item(self, item: str, partition_key: str) -> None:
        """
        Delete item by id and partition key.

        Args:
            item: The document id
            partition_key: The partition key value

        Raises:
            CosmosResourceNotFoundError: If document not found
        """
        partition = self._data.get(partition_key, {})

        if item not in partition:
            raise exceptions.CosmosResourceNotFoundError(
                status_code=404,
                message=f"Document with id '{item}' not found",
            )

        del partition[item]

        # Clean up empty partitions
        if not partition:
            del self._data[partition_key]

    def clear(self):
        """Clear all data (for test cleanup)."""
        self._data.clear()

    def get_all_documents(self) -> list[dict[str, Any]]:
        """Return all documents (for test assertions)."""
        docs = []
        for partition in self._data.values():
            docs.extend(partition.values())
        return docs


class FakeDatabaseClient:
    """Fake database client that returns the container."""

    def __init__(self, container: FakeCosmosContainer):
        self._container = container

    def get_container_client(self, container_name: str) -> FakeCosmosContainer:
        return self._container


@pytest.fixture
def fake_container():
    """Provide a fresh FakeCosmosContainer for each test."""
    container = FakeCosmosContainer()
    yield container
    container.clear()


@pytest.fixture
def fake_cosmos_client_class(fake_container):
    """
    Provide a FakeCosmosClient class that uses the fake_container.
    Returns a class (not instance) for patching CosmosClient.
    """

    class FakeCosmosClient:
        def __init__(self, endpoint: str, credential: Any):
            self._endpoint = endpoint
            self._container = fake_container

        def get_database_client(self, database_name: str):
            return FakeDatabaseClient(self._container)

        async def close(self):
            pass

    return FakeCosmosClient


@pytest.fixture
async def site_config_lookup(fake_cosmos_client_class, fake_container, monkeypatch):
    """
    Provide a CosmosSiteConfigLookup instance with fake Cosmos client injected.

    This patches both:
    1. The CosmosClient import to use the fake
    2. The Azure credential to skip real auth
    """
    from nlweb_cosmos_site_config.site_config_lookup import CosmosSiteConfigLookup

    # Patch CosmosClient
    monkeypatch.setattr(
        "nlweb_cosmos_site_config.site_config_lookup.CosmosClient",
        fake_cosmos_client_class,
    )

    # Patch get_azure_credential to return a dummy
    async def fake_get_credential():
        return "fake-credential"

    monkeypatch.setattr(
        "nlweb_cosmos_site_config.site_config_lookup.get_azure_credential",
        fake_get_credential,
    )

    lookup = CosmosSiteConfigLookup(
        provider_name="test-provider",
        endpoint="https://fake-cosmos.documents.azure.com:443/",
        database_name="test-db",
        container_name="test-container",
        cache_ttl=60,
    )

    yield lookup

    await lookup.close()
