"""
Cosmos DB object storage implementation for storing full schema.org JSON objects.
"""

import config  # Load environment variables
import os
import json
import asyncio
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError
from azure.identity import DefaultAzureCredential
import logging

import log

log.configure(os.environ)
logger = logging.getLogger("cosmos_db")


class CosmosDB:
    """Azure Cosmos DB object storage implementation"""

    def __init__(self):
        # Cosmos DB configuration from environment variables
        self.cosmos_endpoint = os.getenv('COSMOS_DB_ENDPOINT')
        self.database_name = os.getenv('COSMOS_DB_DATABASE_NAME')
        self.container_name = os.getenv('COSMOS_DB_CONTAINER_NAME')

        # Validate required environment variables
        missing_vars = []
        if not self.cosmos_endpoint:
            missing_vars.append('COSMOS_DB_ENDPOINT')
        if not self.database_name:
            missing_vars.append('COSMOS_DB_DATABASE_NAME')
        if not self.container_name:
            missing_vars.append('COSMOS_DB_CONTAINER_NAME')

        if missing_vars:
            raise EnvironmentError(
                f"Missing required Cosmos DB environment variables: {', '.join(missing_vars)}. "
                "Ensure these are set in your .env file or Kubernetes secrets."
            )

        # Always use Azure AD authentication with DefaultAzureCredential
        credential = DefaultAzureCredential()
        self.client = CosmosClient(self.cosmos_endpoint, credential=credential)

        # Get database and container references
        self.database = self.client.get_database_client(self.database_name)
        self.container = self.database.get_container_client(self.container_name)
        logger.info(f"Initialized - endpoint: {self.cosmos_endpoint}, database: {self.database_name}, container: {self.container_name}")

    async def add(self, item: dict):
        """Add or update an item in Cosmos DB"""
        try:
            # Ensure @id exists
            if '@id' not in item:
                logger.warning(f"Item missing @id, skipping")
                return

            # Create a deterministic hash of @id for the system 'id' field
            id_hash = hashlib.sha256(item['@id'].encode('utf-8')).hexdigest()
            
            # Prepare item for Cosmos DB
            cosmos_item = item.copy()
            cosmos_item['id'] = id_hash
            
            # Upsert the item
            def execute_upsert():
                return self.container.upsert_item(body=cosmos_item)
            
            result = await asyncio.get_event_loop().run_in_executor(None, execute_upsert)
            
        except CosmosHttpResponseError as e:
            logger.error(f"Error adding item {item.get('@id')}: {e.message}")
        except Exception as e:
            logger.error(f"Error adding item: {e}")

    async def delete(self, object_id: str):
        """Remove an item from Cosmos DB by its @id"""
        try:
            # Calculate the hash to find the system 'id'
            id_hash = hashlib.sha256(object_id.encode('utf-8')).hexdigest()
            
            # Delete the item
            def execute_delete():
                try:
                    self.container.delete_item(
                        item=id_hash,
                        partition_key=object_id  # The @id is the partition key
                    )
                    return True
                except CosmosResourceNotFoundError:
                    logger.error(f"Item not found for deletion: {object_id}")
                    return False
            
            result = await asyncio.get_event_loop().run_in_executor(None, execute_delete)
            
        except CosmosHttpResponseError as e:
            logger.error(f"Error deleting item {object_id}: {e.message}")
        except Exception as e:
            logger.error(f"Error deleting item: {e}")

    async def batch_add(self, items: List[dict]):
        """Batch add items to Cosmos DB"""
        try:
            logger.debug(f"Starting batch add for {len(items)} items")
            
            # Track duplicates
            id_set = set()
            success_count = 0
            duplicate_count = 0
            error_count = 0
            
            for item in items:
                # Check for @id
                if '@id' not in item:
                    logger.warning("Item missing @id, skipping")
                    error_count += 1
                    continue
                
                # Check for duplicates
                if item['@id'] in id_set:
                    logger.warning(f"⚠️ Duplicate @id found, skipping: {item['@id']}")
                    duplicate_count += 1
                    continue
                
                try:
                    # Create deterministic hash for system 'id'
                    id_hash = hashlib.sha256(item['@id'].encode('utf-8')).hexdigest()
                    
                    # Prepare item
                    cosmos_item = item.copy()
                    cosmos_item['id'] = id_hash
                    
                    # Upsert synchronously (within executor)
                    def execute_upsert():
                        return self.container.upsert_item(body=cosmos_item)
                    
                    await asyncio.get_event_loop().run_in_executor(None, execute_upsert)
                    
                    id_set.add(item['@id'])
                    success_count += 1
                    
                    # Log progress every 100 items
                    if success_count % 100 == 0:
                        logger.debug(f"✅ Uploaded {success_count} items...")
                    
                except CosmosHttpResponseError as e:
                    logger.error(f"❌ Failed to upload {item['@id']}: {e.message}")
                    error_count += 1
                except Exception as e:
                    logger.error(f"❌ Unexpected error uploading {item.get('@id', 'unknown')}: {e}")
                    error_count += 1
            
            logger.info(f"Batch add complete - Success: {success_count}, Duplicates: {duplicate_count}, Errors: {error_count}")
            
        except Exception as e:
            logger.error(f"Error in batch add: {e}")
            import traceback
            traceback.print_exc()

    async def batch_delete(self, object_ids: List[str]):
        """Batch delete items from Cosmos DB"""
        try:
            logger.debug(f"Starting batch delete for {len(object_ids)} items")
            
            success_count = 0
            not_found_count = 0
            error_count = 0
            
            for object_id in object_ids:
                try:
                    # Calculate hash for system 'id'
                    id_hash = hashlib.sha256(object_id.encode('utf-8')).hexdigest()
                    
                    # Delete synchronously (within executor)
                    def execute_delete():
                        try:
                            self.container.delete_item(
                                item=id_hash,
                                partition_key=object_id
                            )
                            return True
                        except CosmosResourceNotFoundError:
                            return False
                    
                    found = await asyncio.get_event_loop().run_in_executor(None, execute_delete)
                    
                    if found:
                        success_count += 1
                        if success_count % 100 == 0:
                            logger.debug(f"✅ Deleted {success_count} items...")
                    else:
                        not_found_count += 1
                    
                except CosmosHttpResponseError as e:
                    logger.error(f"❌ Failed to delete {object_id}: {e.message}")
                    error_count += 1
                except Exception as e:
                    logger.error(f"❌ Unexpected error deleting {object_id}: {e}")
                    error_count += 1
            
            logger.debug(f"Batch delete complete - Success: {success_count}, Not found: {not_found_count}, Errors: {error_count}")
            
        except Exception as e:
            logger.error(f"Error in batch delete: {e}")
            import traceback
            traceback.print_exc()


# Global Cosmos DB instance
_cosmos_db = None

def _get_cosmos_db():
    """Get or create the global Cosmos DB instance"""
    global _cosmos_db
    if _cosmos_db is None:
        _cosmos_db = CosmosDB()
    return _cosmos_db


# Public synchronous API (called by worker.py)
def cosmos_db_add(item: dict):
    """
    Add/update an item in Cosmos DB (synchronous wrapper)
    """
    db = _get_cosmos_db()
    asyncio.run(db.add(item))


def cosmos_db_delete(object_id: str):
    """
    Remove an item from Cosmos DB (synchronous wrapper)
    """
    db = _get_cosmos_db()
    asyncio.run(db.delete(object_id))


def cosmos_db_batch_add(items: List[dict]):
    """
    Batch add items to Cosmos DB (synchronous wrapper)
    Args:
        items: List of JSON objects with @id fields
    """
    db = _get_cosmos_db()
    asyncio.run(db.batch_add(items))


def cosmos_db_batch_delete(object_ids: List[str]):
    """
    Batch delete items from Cosmos DB (synchronous wrapper)
    Args:
        object_ids: List of @id values to delete
    """
    db = _get_cosmos_db()
    asyncio.run(db.batch_delete(object_ids))
