# NLWeb Protocol v0.54 Data Models
# Compliant with NLWeb Protocol Specification v0.54

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, ConfigDict


# ============================================================================
# Request Models
# ============================================================================


class Query(BaseModel):
    """
    Query section - specifies the user's current request.

    Required field:
    - text: The natural language query string

    Fields with defaults:
    - site: Site filter for the query (default: "all")
    - num_results: Number of results to retrieve (default: 50)
    - max_results: Maximum results after ranking (default: 9)
    - min_score: Minimum relevance score threshold (default: 51)

    Optional fields:
    - decontextualized_query: Decontextualized version after processing context

    Properties:
    - effective_query: Returns decontextualized_query if set, otherwise text
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., description="Natural language query from user (required)")
    decontextualized_query: Optional[str] = Field(
        None,
        description="Decontextualized version of the query after processing context (internal use)",
    )
    site: str = Field(
        "all", description='Site filter for the query (use "all" for cross-site search)'
    )
    num_results: int = Field(
        50, ge=1, le=1000, description="Number of results to retrieve from the index"
    )
    max_results: int = Field(
        9, ge=1, le=100, description="Maximum number of results after ranking"
    )
    min_score: int = Field(
        51, ge=0, le=100, description="Minimum relevance score threshold for results"
    )

    @property
    def effective_query(self) -> str:
        """Returns decontextualized_query if set, otherwise text."""
        return self.decontextualized_query or self.text


class Context(BaseModel):
    """Context section - provides contextual information about the query."""

    model_config = ConfigDict(populate_by_name=True, ser_json_by_alias=True)

    schema_type: Optional[str] = Field(
        "ConversationalContext",
        alias="@type",
        serialization_alias="@type",
        description="Type of Context, determines attributes and semantics (default: ConversationalContext)",
    )
    prev: Optional[List[str]] = Field(
        None, description="Array of previous queries in the conversation (optional)"
    )
    text: Optional[str] = Field(
        None,
        description="Free-form text paragraph describing the broader context (optional)",
    )
    memory: Optional[List[str]] = Field(
        None,
        description="Persistent information about the user's preferences, constraints, or characteristics (optional)",
    )


class Prefer(BaseModel):
    """Prefer section - specifies expectations for response format and delivery."""

    streaming: Optional[bool] = Field(
        None,
        description="Boolean indicating whether streaming response is desired (optional)",
    )
    response_format: Optional[str] = Field(
        "chatgpt_app",
        description='Preferred response format: "chatgpt_app" (default) or "conv_search" (optional)',
    )
    mode: Optional[str] = Field(
        None, description="Response mode such as list, summarize, etc. (optional)"
    )
    accept_language: Optional[str] = Field(
        None,
        alias="accept-language",
        description="Language code for the response (e.g., en) (optional)",
    )
    user_agent: Optional[str] = Field(
        None,
        alias="user-agent",
        description="Type of client making the request (mobile, desktop, etc.) (optional)",
    )


class SessionContext(BaseModel):
    """Session context for tracking state across requests."""

    conversation_id: Optional[str] = Field(
        None, description="Conversation identifier (optional)"
    )
    state_token: Optional[str] = Field(
        None, description="Encrypted state blob (optional)"
    )


class Meta(BaseModel):
    """Meta section - contains metadata about the request."""

    api_version: Optional[str] = Field(
        None, description="API version number being used (optional)"
    )
    session_context: Optional[SessionContext] = Field(
        None, description="Session state context (optional)"
    )
    user: Optional[Dict[str, Any]] = Field(
        None, description="User identifier object (optional)"
    )
    remember: Optional[bool] = Field(
        None,
        description="Whether to remember this interaction in conversation history (optional)",
    )
    start_num: Optional[int] = Field(
        0,
        description="The start offset for the returned results"
    )


class AskRequest(BaseModel):
    """NLWeb Ask Request - v0.54 compliant."""

    query: Query = Field(
        ...,
        description="Specifies the user's current request and associated query parameters (required)",
    )
    context: Optional[Context] = Field(
        None,
        description="Provides contextual information about the query (optional)",
    )
    prefer: Optional[Prefer] = Field(
        None,
        description="Specifies expectations for how the response should be formatted and delivered (optional)",
    )
    meta: Optional[Meta] = Field(
        None,
        description="Contains metadata about the request itself (optional)",
    )


# ============================================================================
# Response Models
# ============================================================================


class ResponseType(Enum):
    """Response type enumeration."""

    Answer = "Answer"
    Elicitation = "Elicitation"
    Promise = "Promise"
    Failure = "Failure"


class AskResponseMeta(BaseModel):
    """Response metadata section."""

    response_type: str = Field(
        ...,
        description="Type of response: Answer | Elicitation | Promise | Failure (required)",
    )
    response_format: Optional[str] = Field(
        None,
        description='The response format of the answer: "chatgpt_app" or "conv_search" (optional)',
    )
    version: str = Field(..., description="API version number (required)")
    decontextualized_query: Optional[str] = Field(
        None,
        description="Decontextualized version of the query (included when context was used) (optional)",
    )
    session_context: Optional[SessionContext] = Field(
        None, description="Session context to include in future calls (optional)"
    )


class Grounding(BaseModel):
    """Grounding information for provenance."""

    source_urls: Optional[List[str]] = Field(
        None, description="Source URLs for citations (optional)"
    )
    citations: Optional[List[str]] = Field(
        None, description="Citation references (optional)"
    )


class Action(BaseModel):
    """Action definition for result objects."""

    model_config = ConfigDict(populate_by_name=True, ser_json_by_alias=True)

    schema_context: Optional[str] = Field(
        None,
        alias="@context",
        serialization_alias="@context",
        description="Schema context (e.g., http://schema.org/) (optional)",
    )
    schema_type: Optional[str] = Field(
        None,
        alias="@type",
        serialization_alias="@type",
        description="Action type using schema.org vocabulary (e.g., AddToCartAction) (optional)",
    )
    name: Optional[str] = Field(None, description="Action name (optional)")
    description: Optional[str] = Field(
        None, description="Action description (optional)"
    )
    protocol: Optional[str] = Field(
        None, description="Protocol (e.g., HTTP, MCP, A2A) (optional)"
    )
    method: Optional[str] = Field(
        None, description="HTTP method (e.g., POST, GET) (optional)"
    )
    endpoint: Optional[str] = Field(None, description="Action endpoint URL (optional)")
    params: Optional[Dict[str, Any]] = Field(
        None, description="Action-specific parameters (optional)"
    )


class ResultObject(BaseModel):
    """Individual result object with semi-structured data."""

    model_config = ConfigDict(
        extra="allow", populate_by_name=True, ser_json_by_alias=True
    )

    schema_type: Optional[str] = Field(
        None,
        alias="@type",
        serialization_alias="@type",
        description="Object type using schema.org vocabulary (e.g., Restaurant, Movie, Product, Recipe) (optional)",
    )
    grounding: Optional[Grounding] = Field(
        None, description="Provenance information (optional)"
    )
    actions: Optional[List[Action]] = Field(
        None, description="Executable actions associated with this item (optional)"
    )


class Promise(BaseModel):
    """Promise object for async operations."""

    token: str = Field(..., description="Promise token for checking status (required)")
    estimated_time: Optional[int] = Field(
        None, description="Estimated time to completion in seconds (optional)"
    )


class Question(BaseModel):
    """Elicitation question."""

    id: str = Field(..., description="Question identifier (required)")
    text: str = Field(..., description="Question text (required)")
    type: str = Field(
        ...,
        description="Question type (e.g., single_select, multi_select, text) (required)",
    )
    options: Optional[List[str]] = Field(
        None, description="Options for select-type questions (optional)"
    )


class Elicitation(BaseModel):
    """Elicitation object when agent needs more information."""

    text: str = Field(
        ..., description="Introductory text for the elicitation (required)"
    )
    questions: List[Question] = Field(
        ..., description="List of questions to ask (required)"
    )


class Error(BaseModel):
    """Error object for failure responses."""

    code: str = Field(..., description="Error code (required)")
    message: str = Field(..., description="Error message (required)")


# Answer response models (two formats supported)


class TextContent(BaseModel):
    """Text content for ChatGPT app format."""

    Type: Literal["text"] = Field(..., description='Must be "text" (required)')
    Text: str = Field(..., description="Natural language description (required)")


class AnswerResponseConvSearch(BaseModel):
    """Answer response for conversational search format (conv_search)."""

    field_meta: AskResponseMeta = Field(
        ..., alias="_meta", description="Response metadata (required)"
    )
    results: List[ResultObject] = Field(
        ..., description="Array of typed semi-structured result objects (required)"
    )


class AnswerResponseChatGPT(BaseModel):
    """Answer response for ChatGPT app format (chatgpt_app)."""

    field_meta: AskResponseMeta = Field(
        ..., alias="_meta", description="Response metadata (required)"
    )
    content: List[TextContent] = Field(
        ..., description="Natural language descriptions for LLM consumption (required)"
    )
    structuredData: List[ResultObject] = Field(
        ..., description="Structured data for client consumption (required)"
    )


class PromiseResponse(BaseModel):
    """Promise response for async operations."""

    field_meta: AskResponseMeta = Field(
        ..., alias="_meta", description="Response metadata (required)"
    )
    promise: Promise = Field(..., description="Promise object (required)")


class ElicitationResponse(BaseModel):
    """Elicitation response when more information is needed."""

    field_meta: AskResponseMeta = Field(
        ..., alias="_meta", description="Response metadata (required)"
    )
    elicitation: Elicitation = Field(..., description="Elicitation object (required)")


class FailureResponse(BaseModel):
    """Failure response."""

    field_meta: AskResponseMeta = Field(
        ..., alias="_meta", description="Response metadata (required)"
    )
    error: Error = Field(..., description="Error object (required)")


# ============================================================================
# Await Models
# ============================================================================


class AwaitRequest(BaseModel):
    """Await request to check status of a promise."""

    promise_token: str = Field(
        ..., description="Promise token from previous response (required)"
    )
    action: Literal["checkin", "cancel"] = Field(
        ..., description="Action to perform: checkin or cancel (required)"
    )
    meta: Optional[Meta] = Field(None, description="Request metadata (optional)")


# ============================================================================
# Legacy support models (kept for compatibility with existing code)
# ============================================================================


class Agent(BaseModel):
    model_config = ConfigDict(populate_by_name=True, ser_json_by_alias=True)

    schema_type: str = Field(
        ...,
        alias="@type",
        serialization_alias="@type",
        description='Type of agent, e.g., "Search Agent" or "Analytics Agent". (required)',
    )
    agentSpec: Dict[str, Any] = Field(
        ...,
        description="Agent specification - structure will depend on agent type (required)",
    )


class Resource(BaseModel):
    uri: Optional[str] = Field(
        None,
        description="Resource identifier/template reference (optional)",
    )
    mimeType: Optional[str] = Field(
        None,
        description="MIME type (optional)",
    )
    text: Optional[str] = Field(None, description="Raw content (optional)")
    data: Union[Dict[str, Any], List[Dict[str, Any]]] = Field(
        ...,
        description="Structured data payload (required)",
    )


class ResourceContent(BaseModel):
    type: Literal["resource"] = Field(..., description='must be "resource"')
    resource: Resource = Field(..., description="Resource details")


class ClientType(Enum):
    mobile = "mobile"
    desktop = "desktop"
    tablet = "tablet"
    web = "web"


class ReturnResponse(BaseModel):
    streaming: Optional[bool] = Field(
        True,
        description="Boolean indicating whether streaming response is desired (optional)",
    )
    format: Optional[str] = Field(
        None,
        description="Response format specification (optional)",
    )
    mode: Optional[str] = Field(None, description="Response mode (optional)")
    lang: Optional[str] = Field(
        None,
        description="Language code (optional)",
    )
    client_type: Optional[ClientType] = Field(
        None,
        description="Type of client (optional)",
    )


class WhoRequest(BaseModel):
    query: str = Field(
        ..., description="Natural language query for agent discovery (required)"
    )
    streaming: Optional[bool] = Field(
        True, description="Enable streaming response (optional)"
    )
    conversation_id: Optional[str] = Field(
        None,
        description="Conversational identifier (optional)",
    )
    constr: Optional[Dict[str, Any]] = Field(
        None, description="Additional Constraints (optional)"
    )


class WhoResponseMeta(BaseModel):
    conversation_id: Optional[str] = Field(
        None,
        description="Conversational identifier (optional)",
    )
    version: Optional[str] = Field(None, description="Protocol version (optional)")


class WhoResponse(BaseModel):
    field_meta: WhoResponseMeta = Field(
        ..., alias="_meta", description="Metadata about the response"
    )
    content: List[Union[TextContent, ResourceContent]] = Field(
        ...,
        description="Array of content items containing agent descriptions",
        min_length=1,
    )