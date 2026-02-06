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

from nlweb_core.retriever import ObjectLookupProvider
from nlweb_core.azure_credentials import get_azure_credential

logger = logging.getLogger(__name__)


class CosmosObjectLookup(ObjectLookupProvider):
    """
    Cosmos DB implementation for object lookup.
    Uses Azure AD authentication (DefaultAzureCredential) with native async client.
    """

    def __init__(self, endpoint: str, database_name: str, container_name: str, **kwargs):
        """Initialize Cosmos DB configuration. Client is created lazily on first use."""
        self._endpoint = endpoint
        self._database_name = database_name
        self._container_name = container_name

        # Client initialized lazily on first use
        self._client: Optional[CosmosClient] = None
        self._container_client = None

    async def _ensure_client(self):
        """Create client if not already initialized."""
        if self._client is None:
            credential = await get_azure_credential()
            self._client = CosmosClient(
                self._endpoint,
                credential=credential,
            )
            database = self._client.get_database_client(
                self._database_name
            )
            self._container_client = database.get_container_client(
                self._container_name
            )

    async def get_by_id(self, object_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve object from Cosmos DB by @id field using a Point Read.

        Args:
            object_id: The @id value (typically a URL)

        Returns:
            Complete object dictionary or None if not found
        """
        await self._ensure_client()
        assert self._container_client is not None

        try:
            # Re-calculate the deterministic hash to find the system 'id'
            target_id = hashlib.sha256(object_id.encode("utf-8")).hexdigest()

            # Direct async call - no executor needed
            result = await self._container_client.read_item(
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
            raise

    async def close(self):
        """Close the Cosmos client and release resources."""
        if self._client is not None:
            await self._client.close()
            self._client = None
        self._container_client = None
