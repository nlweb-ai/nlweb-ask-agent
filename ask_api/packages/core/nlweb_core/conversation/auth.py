# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Authorization utilities for conversation API.

Handles user ID extraction and conversation access validation.
"""

import logging
from typing import Optional

from nlweb_core.conversation.storage import ConversationStorageClient
from nlweb_core.protocol.models import Meta

logger = logging.getLogger(__name__)


def get_authenticated_user_id(request_meta: Optional[Meta]) -> Optional[str]:
    """
    Extract user ID from request meta.

    In production, this should validate that meta.user matches
    the authenticated session (from JWT token, OAuth session, etc.)

    Args:
        request_meta: Meta object from the request

    Returns:
        User ID string, or None if not found
    """
    if not request_meta or not request_meta.user:
        return None

    # Handle dict format
    if isinstance(request_meta.user, dict):
        return request_meta.user.get("id") or request_meta.user.get("user_id")

    # Handle object format
    if hasattr(request_meta.user, "id"):
        return request_meta.user.id
    if hasattr(request_meta.user, "user_id"):
        return request_meta.user.user_id

    return None


async def validate_conversation_access(
    conversation_id: str, authenticated_user_id: str, storage: ConversationStorageClient
) -> bool:
    """
    Verify that the authenticated user owns this conversation.

    Args:
        conversation_id: The conversation ID to check
        authenticated_user_id: The authenticated user's ID
        storage: ConversationStorageClient instance

    Returns:
        True if user has access, False otherwise
    """
    try:
        # Get first message to check ownership
        messages = await storage.get_messages(conversation_id, limit=1)

        if not messages:
            # Sanitize conversation_id for logging to prevent log injection
            sanitized_conv_id = conversation_id.replace("\n", "\\n").replace(
                "\r", "\\r"
            )
            logger.warning(f"Conversation {sanitized_conv_id} not found")
            return False

        # Extract user_id from message metadata
        message_user_id = (
            messages[0].metadata.get("user_id") if messages[0].metadata else None
        )

        if not message_user_id:
            # Sanitize conversation_id for logging to prevent log injection
            sanitized_conv_id = conversation_id.replace("\n", "\\n").replace(
                "\r", "\\r"
            )
            logger.warning(
                f"Conversation {sanitized_conv_id} has no user_id in metadata"
            )
            return False

        # Check if user_id matches
        has_access = message_user_id == authenticated_user_id

        if not has_access:
            # Sanitize all user-provided values for logging to prevent log injection
            sanitized_auth_user = authenticated_user_id.replace("\n", "\\n").replace(
                "\r", "\\r"
            )
            sanitized_conv_id = conversation_id.replace("\n", "\\n").replace(
                "\r", "\\r"
            )
            sanitized_msg_user = message_user_id.replace("\n", "\\n").replace(
                "\r", "\\r"
            )
            logger.warning(
                f"Access denied: user {sanitized_auth_user} tried to access "
                f"conversation {sanitized_conv_id} owned by {sanitized_msg_user}"
            )

        return has_access

    except Exception as e:
        logger.error(f"Error validating conversation access: {e}", exc_info=True)
        return False


def validate_session(request, user_id: str) -> bool:
    """
    Validate that the user_id from request matches the authenticated session.

    TODO: Implement actual session validation based on your auth strategy.
    This is a placeholder that should be replaced with:
    - JWT token validation
    - OAuth session validation
    - API key validation
    - or other authentication method

    Args:
        request: aiohttp Request object
        user_id: User ID from request meta

    Returns:
        True if session is valid for this user_id, False otherwise
    """
    # TODO: Implement actual session validation
    # Examples:
    #
    # JWT validation:
    # auth_header = request.headers.get('Authorization')
    # if not auth_header or not auth_header.startswith('Bearer '):
    #     return False
    # token = auth_header[7:]
    # try:
    #     payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
    #     return payload.get('user_id') == user_id
    # except jwt.InvalidTokenError:
    #     return False
    #
    # Session cookie:
    # session = await get_session(request)
    # return session.get('user_id') == user_id
    #
    # API key:
    # api_key = request.headers.get('X-API-Key')
    # user = await get_user_by_api_key(api_key)
    # return user and user.id == user_id

    logger.warning("Session validation not implemented - skipping validation")
    return True  # INSECURE: Remove this after implementing real validation
