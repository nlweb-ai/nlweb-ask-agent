"""
Tests for NLWeb conversation saver module.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from nlweb_core.conversation_saver import ConversationSaver, set_conversation_storage_client, get_conversation_storage_client
from nlweb_core.protocol.models import AskRequest, Query, Meta, SessionContext, Prefer


@pytest.fixture(autouse=True)
def reset_storage_client():
    """Reset the storage client before and after each test."""
    set_conversation_storage_client(None)
    yield
    set_conversation_storage_client(None)


def make_request(
    query_text: str = "test query",
    remember: bool = None,
    user: dict = None,
    conversation_id: str = None,
    site: str = None,
    response_format: str = None,
) -> AskRequest:
    """Helper to create test AskRequest objects."""
    meta = None
    if remember is not None or user is not None or conversation_id is not None:
        session_context = None
        if conversation_id is not None:
            session_context = SessionContext(conversation_id=conversation_id)
        meta = Meta(remember=remember, user=user, session_context=session_context)

    prefer = None
    if response_format is not None:
        prefer = Prefer(response_format=response_format)

    query = Query(text=query_text, decontextualized_query=None)
    if site is not None:
        query.site = site

    return AskRequest(query=query, context=None, prefer=prefer, meta=meta)


class TestConversationSaverInit:
    """Tests for ConversationSaver initialization."""

    def test_gets_storage_client_from_cache(self):
        """Test storage client is retrieved from module cache."""
        mock_client = MagicMock()
        set_conversation_storage_client(mock_client)
        saver = ConversationSaver()
        assert saver.storage_client is mock_client

    def test_storage_client_is_none_when_not_configured(self):
        """Test storage client is None when not set."""
        set_conversation_storage_client(None)
        saver = ConversationSaver()
        assert saver.storage_client is None


class TestGetUserId:
    """Tests for _get_user_id method."""

    def test_returns_none_when_no_meta(self):
        """Test returns None when request has no meta."""
        set_conversation_storage_client(None)
        saver = ConversationSaver()
        request = make_request()
        assert saver._get_user_id(request) is None

    def test_returns_id_from_dict_user(self):
        """Test extracts 'id' from dict-format user."""
        set_conversation_storage_client(None)
        saver = ConversationSaver()
        request = make_request(remember=True, user={"id": "user-123"})
        assert saver._get_user_id(request) == "user-123"

    def test_returns_user_id_from_dict_user(self):
        """Test extracts 'user_id' from dict-format user."""
        set_conversation_storage_client(None)
        saver = ConversationSaver()
        request = make_request(remember=True, user={"user_id": "user-456"})
        assert saver._get_user_id(request) == "user-456"

    def test_prefers_id_over_user_id(self):
        """Test 'id' takes precedence over 'user_id'."""
        set_conversation_storage_client(None)
        saver = ConversationSaver()
        request = make_request(remember=True, user={"id": "id-val", "user_id": "user_id-val"})
        assert saver._get_user_id(request) == "id-val"

    def test_returns_none_for_empty_user_dict(self):
        """Test returns None for empty user dict."""
        set_conversation_storage_client(None)
        saver = ConversationSaver()
        request = make_request(remember=True, user={})
        assert saver._get_user_id(request) is None


class TestGetOrCreateConversationId:
    """Tests for _get_or_create_conversation_id method."""

    def test_returns_existing_conversation_id(self):
        """Test returns conversation_id from session_context."""
        set_conversation_storage_client(None)
        saver = ConversationSaver()
        request = make_request(remember=True, conversation_id="conv-123")
        assert saver._get_or_create_conversation_id(request) == "conv-123"

    def test_generates_uuid_when_no_conversation_id(self):
        """Test generates new UUID when no conversation_id."""
        set_conversation_storage_client(None)
        saver = ConversationSaver()
        request = make_request(remember=True)
        result = saver._get_or_create_conversation_id(request)
        # Should be a valid UUID
        uuid.UUID(result)

    def test_generates_uuid_when_no_meta(self):
        """Test generates new UUID when no meta."""
        set_conversation_storage_client(None)
        saver = ConversationSaver()
        request = make_request()
        result = saver._get_or_create_conversation_id(request)
        uuid.UUID(result)


class TestSave:
    """Tests for save method."""

    @pytest.mark.asyncio
    async def test_returns_early_when_no_storage_client(self):
        """Test returns without saving when storage client is None."""
        set_conversation_storage_client(None)
        saver = ConversationSaver()
        request = make_request(remember=True, user={"id": "user-123"})
        # Should not raise, just return
        await saver.save(request, [])

    @pytest.mark.asyncio
    async def test_returns_early_when_remember_false(self):
        """Test skips saving when remember=False."""
        mock_client = AsyncMock()
        set_conversation_storage_client(mock_client)
        saver = ConversationSaver()
        request = make_request(remember=False, user={"id": "user-123"})
        await saver.save(request, [])
        mock_client.store_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_when_remember_not_set(self):
        """Test skips saving when remember is not set."""
        mock_client = AsyncMock()
        set_conversation_storage_client(mock_client)
        saver = ConversationSaver()
        request = make_request(user={"id": "user-123"})
        await saver.save(request, [])
        mock_client.store_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_when_no_user_id(self):
        """Test skips saving when no user_id."""
        mock_client = AsyncMock()
        set_conversation_storage_client(mock_client)
        saver = ConversationSaver()
        request = make_request(remember=True)
        await saver.save(request, [])
        mock_client.store_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_saves_message_when_conditions_met(self):
        """Test saves message when all conditions are met."""
        mock_client = AsyncMock()
        set_conversation_storage_client(mock_client)
        saver = ConversationSaver()
        request = make_request(
            remember=True,
            user={"id": "user-123"},
            conversation_id="conv-456",
            site="example.com",
            response_format="json",
        )
        results = [{"@type": "Thing", "name": "Test Result", "url": "https://example.com"}]
        await saver.save(request, results)

        mock_client.store_message.assert_called_once()
        message = mock_client.store_message.call_args[0][0]

        assert message.conversation_id == "conv-456"
        assert message.request == request
        assert message.metadata["user_id"] == "user-123"
        assert message.metadata["site"] == "example.com"
        assert message.metadata["response_format"] == "json"
        assert len(message.results) == 1

    @pytest.mark.asyncio
    async def test_saves_with_empty_results(self):
        """Test saves message with empty results list."""
        mock_client = AsyncMock()
        set_conversation_storage_client(mock_client)
        saver = ConversationSaver()
        request = make_request(remember=True, user={"id": "user-123"})
        await saver.save(request, [])

        mock_client.store_message.assert_called_once()
        message = mock_client.store_message.call_args[0][0]
        assert message.results is None

    @pytest.mark.asyncio
    async def test_logs_error_on_storage_failure(self):
        """Test logs error but doesn't raise when storage fails."""
        mock_client = AsyncMock()
        mock_client.store_message.side_effect = Exception("Storage error")
        set_conversation_storage_client(mock_client)
        with patch("nlweb_core.conversation_saver.logger") as mock_logger:
            saver = ConversationSaver()
            request = make_request(remember=True, user={"id": "user-123"})
            # Should not raise
            await saver.save(request, [])
            mock_logger.error.assert_called_once()
            assert "Failed to save conversation turn" in mock_logger.error.call_args[0][0]
