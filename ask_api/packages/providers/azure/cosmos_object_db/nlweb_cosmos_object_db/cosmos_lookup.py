# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Azure Cosmos DB implementation for object lookup.
"""

import hashlib
import logging
from typing import Dict, Any, Optional
from azure.cosmos.aio import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential

from nlweb_core.retriever import ObjectLookupInterface
from nlweb_core.config import get_config

logger = logging.getLogger(__name__)


class CosmosObjectLookup(ObjectLookupInterface):
    """
    Cosmos DB implementation for object lookup.
    Uses Azure AD authentication (DefaultAzureCredential) with native async client.
    """

    def __init__(self):
        """Initialize Cosmos DB configuration. Client is created lazily on first use."""
        config = get_config()
        if not config.object_storage or not config.object_storage.enabled:
            raise ValueError("Object storage is not enabled in configuration")

        self._storage_config = config.object_storage

        if not self._storage_config.endpoint:
            raise ValueError("Cosmos DB endpoint not configured")

        # Client initialized lazily on first use
        self._client: Optional[CosmosClient] = None
        self._credential: Optional[DefaultAzureCredential] = None
        self._container = None

    def _ensure_client(self):
        """Create client if not already initialized."""
        if self._client is None:
            # These are validated in __init__, assert for type checker
            assert self._storage_config.endpoint is not None
            assert self._storage_config.database_name is not None
            assert self._storage_config.container_name is not None

            self._credential = DefaultAzureCredential()
            self._client = CosmosClient(
                self._storage_config.endpoint,
                credential=self._credential,
            )
            database = self._client.get_database_client(
                self._storage_config.database_name
            )
            self._container = database.get_container_client(
                self._storage_config.container_name
            )

    async def get_by_id(self, object_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve object from Cosmos DB by @id field using a Point Read.

        Args:
            object_id: The @id value (typically a URL)

        Returns:
            Complete object dictionary or None if not found
        """
        self._ensure_client()
        assert self._container is not None

        try:
            # Re-calculate the deterministic hash to find the system 'id'
            target_id = hashlib.sha256(object_id.encode("utf-8")).hexdigest()

            # Direct async call - no executor needed
            result = await self._container.read_item(
                item=target_id,
                partition_key=object_id,  # The object_id (URL) is the partition key
            )

            # Remove Cosmos DB metadata fields before returning
            if result:
                cosmos_metadata_fields = [
                    "_rid",
                    "_self",
                    "_etag",
                    "_attachments",
                    "_ts",
                    "id",
                ]
                for field in cosmos_metadata_fields:
                    result.pop(field, None)

            return result

        except CosmosResourceNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Error fetching object {object_id} from Cosmos DB: {e}")
            return None

    async def close(self):
        """Close the Cosmos client and release resources."""
        if self._client is not None:
            await self._client.close()
            self._client = None
        if self._credential is not None:
            await self._credential.close()
            self._credential = None
        self._container = None
