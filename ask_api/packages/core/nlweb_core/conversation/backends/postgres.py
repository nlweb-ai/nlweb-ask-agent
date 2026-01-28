# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
PostgreSQL conversation storage backend.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

import asyncpg
import asyncio
import logging
from typing import List, Optional
from datetime import datetime, timezone
import json

from nlweb_core.conversation.storage import ConversationStorageInterface
from nlweb_core.conversation.models import ConversationMessage
from nlweb_core.protocol.models import AskRequest, ResultObject
from nlweb_core.db_utils import with_db_retry

logger = logging.getLogger(__name__)


class PostgresStorage(ConversationStorageInterface):
    """PostgreSQL backend for conversation storage."""

    def __init__(self, config):
        """
        Initialize PostgreSQL storage.

        Args:
            config: ConversationStorageConfig with connection details
        """
        self.config = config
        self.pool = None
        self._schema_initialized = False
        self._schema_lock = asyncio.Lock()  # Thread-safe schema initialization

    async def initialize(self):
        """
        Initialize connection pool and schema.

        Should be called during server startup to avoid first-request latency.
        """
        await self._get_pool()
        await self._ensure_schema_exists()
        logger.info("PostgreSQL storage initialized")

    async def _get_pool(self):
        """Get or create connection pool."""
        if not self.pool:
            # Build connection string
            if self.config.connection_string:
                conn_str = self.config.connection_string
            else:
                # Build from components
                password = self.config.password or ''
                conn_str = (
                    f"postgresql://{self.config.user}:{password}"
                    f"@{self.config.host}:{self.config.port or 5432}"
                    f"/{self.config.database_name}"
                )

            try:
                self.pool = await asyncpg.create_pool(
                    conn_str,
                    min_size=2,
                    max_size=10,
                    command_timeout=60
                )
                logger.info("PostgreSQL connection pool created")
            except Exception as e:
                logger.error(f"Failed to create PostgreSQL pool: {e}")
                raise

        return self.pool

    async def _ensure_schema_exists(self):
        """Create schema if it doesn't exist (lazy initialization)."""
        # Fast path - no lock needed
        if self._schema_initialized:
            return

        # Slow path - acquire lock for schema creation
        async with self._schema_lock:
            # Double-check after acquiring lock
            if self._schema_initialized:
                return

            pool = await self._get_pool()

            async with pool.acquire() as conn:
                try:
                    # Check if table exists
                    exists = await conn.fetchval('''
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables
                            WHERE table_name = 'conversations'
                        )
                    ''')

                    if not exists:
                        logger.info("Creating conversations table and indexes...")

                        # Create table
                        await conn.execute('''
                            CREATE TABLE conversations (
                                id BIGSERIAL PRIMARY KEY,
                                message_id VARCHAR(255) UNIQUE NOT NULL,
                                conversation_id VARCHAR(255) NOT NULL,
                                user_id VARCHAR(255),
                                site VARCHAR(255),
                                timestamp TIMESTAMPTZ NOT NULL,
                                request JSONB NOT NULL,
                                results JSONB,
                                metadata JSONB,
                                created_at TIMESTAMPTZ DEFAULT NOW(),
                                updated_at TIMESTAMPTZ DEFAULT NOW()
                            )
                        ''')

                        # Create indexes
                        await conn.execute('''
                            CREATE INDEX idx_conversation_id ON conversations(conversation_id)
                        ''')
                        await conn.execute('''
                            CREATE INDEX idx_user_id ON conversations(user_id)
                        ''')
                        await conn.execute('''
                            CREATE INDEX idx_timestamp ON conversations(timestamp)
                        ''')
                        logger.info("Conversations table and indexes created successfully")
                    else:
                        logger.info("[PostgreSQL] Conversations table already exists")

                    self._schema_initialized = True

                except Exception as e:
                    logger.error(f"Failed to ensure schema exists: {e}")
                    raise

    def _message_to_row(self, message: ConversationMessage) -> tuple:
        """Convert ConversationMessage to database row values."""
        user_id = message.metadata.get('user_id') if message.metadata else None
        site = message.metadata.get('site') if message.metadata else None

        # Serialize request and results as JSON strings for JSONB columns
        # by_alias=True ensures @type is used instead of schema_type
        # Use separators=(',', ':') to remove whitespace and compress JSON
        request_dict = message.request.model_dump(mode='json', by_alias=True) if hasattr(message.request, 'model_dump') else message.request
        request_json = json.dumps(request_dict, separators=(',', ':'))

        results_json = None
        if message.results:
            results_list = [
                r.model_dump(mode='json', by_alias=True) if hasattr(r, 'model_dump') else r
                for r in message.results
            ]
            results_json = json.dumps(results_list, separators=(',', ':'))

        metadata_json = json.dumps(message.metadata, separators=(',', ':')) if message.metadata else None

        return (
            message.message_id,
            message.conversation_id,
            user_id,
            site,
            message.timestamp,
            request_json,  # JSON string for JSONB column
            results_json,  # JSON string for JSONB column
            metadata_json,  # JSON string for JSONB column
        )

    def _row_to_message(self, row: dict) -> ConversationMessage:
        """Convert database row to ConversationMessage."""
        # asyncpg returns JSONB columns as Python dicts/lists directly
        request = AskRequest(**row['request'])

        results = None
        if row.get('results'):
            results = [ResultObject(**r) for r in row['results']]

        metadata = row.get('metadata')

        return ConversationMessage(
            message_id=row['message_id'],
            conversation_id=row['conversation_id'],
            timestamp=row['timestamp'],
            request=request,
            results=results,
            metadata=metadata
        )

    @with_db_retry(max_retries=3, initial_backoff=0.5)
    async def store_message(self, message: ConversationMessage) -> None:
        """Store a conversation message."""
        await self._ensure_schema_exists()

        pool = await self._get_pool()
        values = self._message_to_row(message)

        async with pool.acquire() as conn:
            try:
                await conn.execute('''
                    INSERT INTO conversations
                    (message_id, conversation_id, user_id, site, timestamp, request, results, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ''', *values)

                logger.info(
                    f"Stored message: conv_id={message.conversation_id}, "
                    f"user={values[2]}, msg_id={message.message_id}"
                )
            except asyncpg.UniqueViolationError:
                # Message already exists (duplicate message_id) - NOT a transient error
                logger.warning(f"Message {message.message_id} already exists, skipping")
            except Exception as e:
                logger.error(f"Failed to store message: {e}", exc_info=True)
                raise

    @with_db_retry(max_retries=3, initial_backoff=0.5)
    async def get_messages(
        self,
        conversation_id: str,
        limit: int = 100
    ) -> List[ConversationMessage]:
        """Get messages for a conversation, ordered by timestamp."""
        await self._ensure_schema_exists()

        pool = await self._get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT message_id, conversation_id, user_id, site, timestamp,
                       request, results, metadata
                FROM conversations
                WHERE conversation_id = $1
                ORDER BY timestamp ASC
                LIMIT $2
            ''', conversation_id, limit)

            messages = [self._row_to_message(dict(row)) for row in rows]
            logger.info(f"Retrieved {len(messages)} messages for conversation: {conversation_id}")
            return messages

    @with_db_retry(max_retries=3, initial_backoff=0.5)
    async def get_user_conversations(
        self,
        user_id: str,
        limit: int = 20
    ) -> List[str]:
        """Get conversation IDs for a user, ordered by most recent activity."""
        await self._ensure_schema_exists()

        pool = await self._get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT conversation_id, MAX(timestamp) as last_activity
                FROM conversations
                WHERE user_id = $1
                GROUP BY conversation_id
                ORDER BY last_activity DESC
                LIMIT $2
            ''', user_id, limit)

            conversation_ids = [row['conversation_id'] for row in rows]
            logger.info(f"Retrieved {len(conversation_ids)} conversations for user: {user_id}")
            return conversation_ids

    @with_db_retry(max_retries=3, initial_backoff=0.5)
    async def delete_conversation(self, conversation_id: str) -> None:
        """Delete all messages in a conversation."""
        await self._ensure_schema_exists()

        pool = await self._get_pool()

        async with pool.acquire() as conn:
            result = await conn.execute('''
                DELETE FROM conversations WHERE conversation_id = $1
            ''', conversation_id)

            # Extract count from result string like "DELETE 5"
            count = int(result.split()[-1]) if result else 0
            logger.info(f"Deleted {count} messages for conversation: {conversation_id}")

    async def close(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL connection pool closed")
