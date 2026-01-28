# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Qdrant conversation storage backend.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

from typing import List, Optional
from datetime import datetime
import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from nlweb_core.conversation.storage import ConversationStorageInterface
from nlweb_core.conversation.models import ConversationMessage


class QdrantStorage(ConversationStorageInterface):
    """
    Qdrant-based storage backend for conversations.

    Stores conversation messages as documents in a Qdrant collection,
    using metadata filtering to retrieve messages by conversation_id or user_id.
    """

    def __init__(self, config):
        """
        Initialize Qdrant storage.

        Args:
            config: ConversationStorageConfig with Qdrant connection details
        """
        self.config = config
        self.collection_name = config.collection_name or "nlweb_conversations"

        # Initialize Qdrant client
        if config.url:
            # Remote Qdrant
            self.client = AsyncQdrantClient(
                url=config.url,
                api_key=config.api_key
            )
        elif config.database_path:
            # Local Qdrant
            self.client = AsyncQdrantClient(path=config.database_path)
        else:
            raise ValueError("Qdrant storage requires either 'url' or 'database_path'")

        # Collection will be created on first use
        self._collection_initialized = False

    async def _ensure_collection_exists(self):
        """Create the collection if it doesn't exist."""
        if self._collection_initialized:
            return

        # Check if collection exists
        collections = await self.client.get_collections()
        collection_exists = any(
            col.name == self.collection_name
            for col in collections.collections
        )

        if not collection_exists:
            # Create collection without vectors - we're using it as a document store
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={},  # No vectors needed
            )

        self._collection_initialized = True

    async def store_message(self, message: ConversationMessage) -> None:
        """
        Store a conversation message in Qdrant.

        Args:
            message: The message to store
        """
        await self._ensure_collection_exists()

        # Convert message to dict for storage
        payload = message.model_dump(mode='json')

        # Generate a unique point ID
        point_id = str(uuid.uuid4())

        # Store as a point without vectors
        await self.client.upsert(
            collection_name=self.collection_name,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector={},  # Empty vector
                    payload=payload
                )
            ]
        )

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
        await self._ensure_collection_exists()

        # Scroll through all points with matching conversation_id
        result = await self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="conversation_id",
                        match=models.MatchValue(value=conversation_id)
                    )
                ]
            ),
            limit=limit,
            with_payload=True,
            with_vectors=False
        )

        points = result[0]  # First element is the list of points

        # Convert points to ConversationMessage objects
        messages = []
        for point in points:
            payload = point.payload
            # Convert timestamp string back to datetime
            if isinstance(payload.get('timestamp'), str):
                payload['timestamp'] = datetime.fromisoformat(payload['timestamp'])
            messages.append(ConversationMessage(**payload))

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
        await self._ensure_collection_exists()

        # Scroll through all points with matching user_id in metadata
        result = await self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.user_id",
                        match=models.MatchValue(value=user_id)
                    )
                ]
            ),
            limit=1000,  # Get more to aggregate by conversation
            with_payload=True,
            with_vectors=False
        )

        points = result[0]

        # Extract unique conversation_ids with their latest timestamp
        conversation_times = {}
        for point in points:
            conv_id = point.payload['conversation_id']
            timestamp_str = point.payload['timestamp']
            timestamp = datetime.fromisoformat(timestamp_str)

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
        await self._ensure_collection_exists()

        # Delete all points with matching conversation_id
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="conversation_id",
                            match=models.MatchValue(value=conversation_id)
                        )
                    ]
                )
            )
        )
