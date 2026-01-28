# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Pydantic models for Conversation API endpoints.

These models define the request/response structures for conversation management,
following the same pattern as the NLWeb /ask endpoint.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

from nlweb_core.protocol.models import Meta, AskRequest, ResultObject


# ============================================================================
# Request Models
# ============================================================================

class ConversationFilter(BaseModel):
    """Filter criteria for listing conversations."""
    site: Optional[str] = Field(None, description="Filter by site")
    date_from: Optional[datetime] = Field(None, description="Start date filter")
    date_to: Optional[datetime] = Field(None, description="End date filter")


class Pagination(BaseModel):
    """Pagination parameters."""
    limit: int = Field(20, ge=1, le=100, description="Number of items to return")
    offset: int = Field(0, ge=0, description="Number of items to skip")


class ListConversationsRequest(BaseModel):
    """Request to list conversations for a user."""
    meta: Meta = Field(..., description="Request metadata with user info")
    filter: Optional[ConversationFilter] = Field(None, description="Filter criteria")
    pagination: Optional[Pagination] = Field(
        default_factory=Pagination,
        description="Pagination parameters"
    )


class GetConversationRequest(BaseModel):
    """Request to get messages for a specific conversation."""
    meta: Meta = Field(..., description="Request metadata with user info")
    pagination: Optional[Pagination] = Field(
        default_factory=lambda: Pagination(limit=100),
        description="Pagination parameters"
    )


class DeleteConversationRequest(BaseModel):
    """Request to delete a conversation."""
    meta: Meta = Field(..., description="Request metadata with user info")


class ConversationSearchFilter(BaseModel):
    """Search filter criteria."""
    site: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class ConversationSearch(BaseModel):
    """Search parameters for conversations."""
    query: str = Field(..., description="Search query text")
    filter: Optional[ConversationSearchFilter] = None


class SearchConversationsRequest(BaseModel):
    """Request to search conversations."""
    meta: Meta = Field(..., description="Request metadata with user info")
    search: ConversationSearch = Field(..., description="Search parameters")
    pagination: Optional[Pagination] = Field(
        default_factory=Pagination,
        description="Pagination parameters"
    )


# ============================================================================
# Response Models
# ============================================================================

class ConversationPreview(BaseModel):
    """Preview of conversation content."""
    query: str = Field(..., description="First query in conversation")
    result_count: int = Field(..., description="Number of results returned")


class ConversationSummary(BaseModel):
    """Summary of a conversation."""
    conversation_id: str
    message_count: int
    first_message_timestamp: datetime
    last_message_timestamp: datetime
    site: Optional[str]
    preview: ConversationPreview


class PaginationResponse(BaseModel):
    """Pagination metadata in response."""
    total: int = Field(..., description="Total number of items")
    limit: int = Field(..., description="Items per page")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="Whether more items exist")


class ListConversationsResponse(BaseModel):
    """Response with list of conversations."""
    field_meta: Dict[str, Any] = Field(..., alias="_meta")
    conversations: List[ConversationSummary]
    pagination: PaginationResponse


class ConversationInfo(BaseModel):
    """Information about a conversation."""
    conversation_id: str
    user_id: str
    created_at: datetime
    updated_at: datetime


class ConversationMessage(BaseModel):
    """A single message in the conversation."""
    message_id: str
    timestamp: datetime
    request: AskRequest
    results: Optional[List[ResultObject]]
    metadata: Optional[Dict[str, Any]]


class GetConversationResponse(BaseModel):
    """Response with conversation messages."""
    field_meta: Dict[str, Any] = Field(..., alias="_meta")
    conversation: ConversationInfo
    messages: List[ConversationMessage]
    pagination: PaginationResponse


class DeleteConversationResponse(BaseModel):
    """Response confirming conversation deletion."""
    field_meta: Dict[str, Any] = Field(..., alias="_meta")
    conversation_id: str
    status: str = "deleted"
    messages_deleted: int


class SearchMatch(BaseModel):
    """A search result match."""
    conversation_id: str
    message_id: str
    match_type: str = Field(..., description="Type of match: query, result, metadata")
    match_text: str = Field(..., description="Text that matched")
    timestamp: datetime
    context: Dict[str, Any] = Field(..., description="Context around the match")


class SearchConversationsResponse(BaseModel):
    """Response with search results."""
    field_meta: Dict[str, Any] = Field(..., alias="_meta")
    results: List[SearchMatch]
    pagination: PaginationResponse


class ErrorResponse(BaseModel):
    """Error response."""
    field_meta: Dict[str, Any] = Field(..., alias="_meta")
    error: Dict[str, str] = Field(..., description="Error details with code and message")
