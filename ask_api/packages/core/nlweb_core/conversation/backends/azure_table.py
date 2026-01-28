# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Azure Table Storage conversation storage backend.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

from typing import List
from datetime import datetime
import json

from nlweb_core.conversation.storage import ConversationStorageInterface
from nlweb_core.conversation.models import ConversationMessage

# Lazy imports to avoid requiring azure.data.tables when not using this backend
_azure_imports_done = False
TableServiceClient = None
TableClient = None
ResourceExistsError = None
ResourceNotFoundError = None
DefaultAzureCredential = None

def _ensure_azure_imports():
    """Import Azure dependencies only when needed."""
    global _azure_imports_done, TableServiceClient, TableClient
    global ResourceExistsError, ResourceNotFoundError, DefaultAzureCredential

    if not _azure_imports_done:
        from azure.data.tables.aio import TableServiceClient as TSC, TableClient as TC
        from azure.core.exceptions import ResourceExistsError as REE, ResourceNotFoundError as RNFE
        from azure.identity.aio import DefaultAzureCredential as DAC

        TableServiceClient = TSC
        TableClient = TC
        ResourceExistsError = REE
        ResourceNotFoundError = RNFE
        DefaultAzureCredential = DAC
        _azure_imports_done = True


class AzureTableStorage(ConversationStorageInterface):
    """
    Azure Table Storage backend for conversations.

    Partition strategy:
    - PartitionKey: user_id (enables fast queries for all user conversations)
    - RowKey: conversation_id_timestamp (enables ordering and uniqueness)

    This allows efficient queries for:
    - All conversations for a user
    - Filtering by site in application code
    """

    def __init__(self, config):
        """
        Initialize Azure Table Storage.

        Args:
            config: ConversationStorageConfig with connection details
        """
        # Import Azure dependencies
        _ensure_azure_imports()

        self.config = config
        self.table_name = config.table_name or "conversations"

        # Support both connection string and Azure AD authentication
        if config.connection_string:
            # Use connection string (shared key)
            self.table_service_client = TableServiceClient.from_connection_string(
                conn_str=config.connection_string
            )
        elif config.host and config.auth_method == 'azure_ad':
            # Use Azure AD (managed identity)
            account_url = f"https://{config.host}.table.core.windows.net"
            credential = DefaultAzureCredential()
            self.table_service_client = TableServiceClient(
                endpoint=account_url,
                credential=credential
            )
        else:
            raise ValueError("Azure Table Storage requires either connection_string or (host + auth_method='azure_ad')")

        # Get table client
        self.table_client = self.table_service_client.get_table_client(self.table_name)
        self._table_initialized = False

    async def _ensure_table_exists(self):
        """Create the table if it doesn't exist (lazy initialization)."""
        if self._table_initialized:
            return

        try:
            await self.table_service_client.create_table(self.table_name)
        except ResourceExistsError:
            # Table already exists, that's fine
            pass

        self._table_initialized = True

    def _message_to_entity(self, message: ConversationMessage) -> dict:
        """
        Convert ConversationMessage to Azure Table entity.

        PartitionKey: user_id (from metadata)
        RowKey: conversation_id + timestamp (for ordering and uniqueness)
        """
        user_id = message.metadata.get('user_id', 'anonymous') if message.metadata else 'anonymous'

        # Create RowKey with timestamp for ordering
        timestamp_str = message.timestamp.strftime('%Y%m%d%H%M%S%f')
        row_key = f"{message.conversation_id}_{timestamp_str}"

        # Serialize request and results to JSON
        entity = {
            'PartitionKey': user_id,
            'RowKey': row_key,
            'message_id': message.message_id,
            'conversation_id': message.conversation_id,
            'timestamp': message.timestamp.isoformat(),
            'request': json.dumps(message.request.model_dump(mode='json')),
            'results': json.dumps([r.model_dump(mode='json') for r in message.results]) if message.results else None,
            'metadata': json.dumps(message.metadata) if message.metadata else None,
            'site': message.metadata.get('site') if message.metadata else None,  # Denormalized for easier filtering
        }

        return entity

    def _entity_to_message(self, entity: dict) -> ConversationMessage:
        """Convert Azure Table entity to ConversationMessage."""
        from nlweb_core.protocol.models import AskRequest, ResultObject

        # Parse JSON fields
        request_data = json.loads(entity['request'])
        request = AskRequest(**request_data)

        results = None
        if entity.get('results'):
            results_data = json.loads(entity['results'])
            results = [ResultObject(**r) for r in results_data]

        metadata = None
        if entity.get('metadata'):
            metadata = json.loads(entity['metadata'])

        return ConversationMessage(
            message_id=entity['message_id'],
            conversation_id=entity['conversation_id'],
            timestamp=datetime.fromisoformat(entity['timestamp']),
            request=request,
            results=results,
            metadata=metadata
        )

    async def store_message(self, message: ConversationMessage) -> None:
        """
        Store a conversation message in Azure Table Storage.

        Args:
            message: The message to store
        """
        await self._ensure_table_exists()
        entity = self._message_to_entity(message)
        await self.table_client.create_entity(entity=entity)

    async def get_messages(
        self,
        conversation_id: str,
        limit: int = 100
    ) -> List[ConversationMessage]:
        """
        Get messages for a conversation.

        Args:
            conversation_id: The conversation ID
            limit: Maximum number of messages to return

        Returns:
            List of messages ordered by timestamp
        """
        await self._ensure_table_exists()

        # Query for all messages with this conversation_id (cross-partition query)
        query_filter = f"conversation_id eq '{conversation_id}'"

        entities = self.table_client.query_entities(
            query_filter=query_filter,
            select=['PartitionKey', 'RowKey', 'message_id', 'conversation_id', 'timestamp',
                   'request', 'results', 'metadata', 'site']
        )

        messages = []
        async for entity in entities:
            messages.append(self._entity_to_message(entity))
            if len(messages) >= limit:
                break

        # Sort by timestamp
        messages.sort(key=lambda m: m.timestamp)

        return messages

    async def get_user_conversations(
        self,
        user_id: str,
        limit: int = 20
    ) -> List[str]:
        """
        Get conversation IDs for a specific user.

        Args:
            user_id: The user ID
            limit: Maximum number of conversation IDs to return

        Returns:
            List of conversation IDs ordered by most recent activity
        """
        await self._ensure_table_exists()

        # Query by PartitionKey (user_id) - fast single-partition query
        query_filter = f"PartitionKey eq '{user_id}'"

        entities = self.table_client.query_entities(
            query_filter=query_filter,
            select=['conversation_id', 'timestamp']
        )

        # Group by conversation_id and get latest timestamp
        conversation_times = {}
        async for entity in entities:
            conv_id = entity['conversation_id']
            timestamp = datetime.fromisoformat(entity['timestamp'])

            if conv_id not in conversation_times or timestamp > conversation_times[conv_id]:
                conversation_times[conv_id] = timestamp

        # Sort by most recent and return conversation IDs
        sorted_convs = sorted(
            conversation_times.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return [conv_id for conv_id, _ in sorted_convs[:limit]]

    async def delete_conversation(self, conversation_id: str) -> None:
        """
        Delete all messages in a conversation.

        Args:
            conversation_id: The conversation ID to delete
        """
        await self._ensure_table_exists()

        # Query for all messages in this conversation
        query_filter = f"conversation_id eq '{conversation_id}'"

        entities = self.table_client.query_entities(
            query_filter=query_filter,
            select=['PartitionKey', 'RowKey']
        )

        # Delete each entity
        async for entity in entities:
            try:
                await self.table_client.delete_entity(
                    partition_key=entity['PartitionKey'],
                    row_key=entity['RowKey']
                )
            except ResourceNotFoundError:
                # Entity already deleted, continue
                pass
