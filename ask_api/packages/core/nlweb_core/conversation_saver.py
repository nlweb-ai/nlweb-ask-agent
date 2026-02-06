# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Conversation saver for persisting conversation turns.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from nlweb_core.conversation.models import ConversationMessage
from nlweb_core.protocol.models import AskRequest, ResultObject

logger = logging.getLogger(__name__)


# Module-level cache for conversation storage client
_conversation_storage_client = None


def get_conversation_storage_client():
    """Get the cached conversation storage client."""
    return _conversation_storage_client


def set_conversation_storage_client(client):
    """Set the conversation storage client (called at server startup)."""
    global _conversation_storage_client
    _conversation_storage_client = client


class ConversationSaver:
    """Handles saving conversation turns to storage."""

    def __init__(self):
        self.storage_client = self._get_storage_client()

    def _get_storage_client(self):
        """Get storage client from module-level cache."""
        return get_conversation_storage_client()

    def _get_or_create_conversation_id(self, request: AskRequest) -> str:
        """Get conversation_id from meta.session_context or create new one."""
        meta = request.meta
        if meta and meta.session_context and meta.session_context.conversation_id:
            return meta.session_context.conversation_id
        return str(uuid.uuid4())

    def _get_user_id(self, request: AskRequest) -> Optional[str]:
        """Extract user_id from meta.user if available."""
        meta = request.meta
        if meta and meta.user:
            if isinstance(meta.user, dict):
                return meta.user.get("id") or meta.user.get("user_id")
            elif hasattr(meta.user, "id"):
                return meta.user.id
        return None

    async def save(
        self,
        request: AskRequest,
        results: list[dict],
    ) -> None:
        """
        Save a conversation turn if conditions are met.

        Args:
            request: The AskRequest being processed
            results: The ranked results (list of dicts)
        """
        if not self.storage_client:
            return

        meta = request.meta
        # Only save if meta.remember is explicitly set to True
        if not (meta and meta.remember):
            return

        # Don't save if no user_id (anonymous conversations)
        user_id = self._get_user_id(request)
        if not user_id:
            return

        try:
            # Convert result dicts to ResultObject models
            result_objects = None
            if results:
                result_objects = [
                    ResultObject(**r) if isinstance(r, dict) else r for r in results
                ]

            prefer = request.prefer
            message = ConversationMessage(
                message_id=str(uuid.uuid4()),
                conversation_id=self._get_or_create_conversation_id(request),
                timestamp=datetime.now(timezone.utc),
                request=request,
                results=result_objects,
                metadata={
                    "user_id": user_id,
                    "site": request.query.site,
                    "response_format": prefer.response_format if prefer else None,
                },
            )

            await self.storage_client.store_message(message)
        except Exception as e:
            # Don't fail the query if storage fails
            logger.error(f"Failed to save conversation turn: {e}", exc_info=True)
