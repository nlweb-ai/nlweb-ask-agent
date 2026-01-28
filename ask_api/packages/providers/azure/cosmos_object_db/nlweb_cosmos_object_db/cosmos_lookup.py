# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Azure Cosmos DB implementation for object lookup.
"""

import asyncio
import hashlib
from typing import Dict, Any, Optional
from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity import DefaultAzureCredential

from nlweb_core.retriever import ObjectLookupInterface
from nlweb_core.config import get_config


class CosmosObjectLookup(ObjectLookupInterface):
    """
    Cosmos DB implementation for object lookup.
    Uses Azure AD authentication (DefaultAzureCredential).
    """

    def __init__(self):
        """Initialize Cosmos DB client using get_config().object_storage."""
        config = get_config()
        if not config.object_storage or not config.object_storage.enabled:
            raise ValueError("Object storage is not enabled in configuration")

        self.config = config.object_storage
        
        if not self.config.endpoint:
            raise ValueError("Cosmos DB endpoint not configured")

        # Always use Azure AD authentication
        credential = DefaultAzureCredential()
        self.client = CosmosClient(self.config.endpoint, credential=credential)
        
        # Get database and container
        self.database = self.client.get_database_client(self.config.database_name)
        self.container = self.database.get_container_client(self.config.container_name)

    async def get_by_id(self, object_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve object from Cosmos DB by @id field using a Point Read.
        
        Args:
            object_id: The @id value (typically a URL)
            
        Returns:
            Complete object dictionary or None if not found
        """
        try:
            # Re-calculate the deterministic hash to find the system 'id'
            target_id = hashlib.sha256(object_id.encode('utf-8')).hexdigest()

            def execute_point_read():
                try:
                    # read_item is a direct key-value lookup (1 RU cost)
                    return self.container.read_item(
                        item=target_id, 
                        partition_key=object_id  # The object_id (ie. URL of the object) is the partition key
                    )
                except CosmosResourceNotFoundError:
                    return None

            result = await asyncio.get_event_loop().run_in_executor(None, execute_point_read)
            
            # Remove Cosmos DB metadata fields before returning
            if result:
                # Remove system fields that start with underscore and 'id' field (we have @id)
                cosmos_metadata_fields = ['_rid', '_self', '_etag', '_attachments', '_ts', 'id']
                for field in cosmos_metadata_fields:
                    result.pop(field, None)
            
            return result

        except Exception as e:
            print(f"Error fetching object {object_id} from Cosmos DB: {e}")
            return None
