"""
NLWeb Protocol Data Models

These models define the data contracts for the NLWeb protocol.
Generated from TypeSpec specification at: https://github.com/nlweb-ai/nlweb-typespec

DO NOT EDIT models.py directly - regenerate from TypeSpec instead.
"""

from .models import (
    Agent,
    ResponseType,
    AskResponseMeta,
    Context,
    Meta,
    Query,
    Prefer,
    Resource,
    ResourceContent,
    ClientType,
    ReturnResponse,
    TextContent,
    WhoRequest,
    WhoResponseMeta,
    AskRequest,
    AnswerResponseConvSearch,
    AnswerResponseChatGPT,
    PromiseResponse,
    ElicitationResponse,
    FailureResponse,
    AwaitRequest,
    WhoResponse,
)

__all__ = [
    "Agent",
    "ResponseType",
    "AskResponseMeta",
    "Context",
    "Meta",
    "Query",
    "Prefer",
    "Resource",
    "ResourceContent",
    "ClientType",
    "ReturnResponse",
    "TextContent",
    "WhoRequest",
    "WhoResponseMeta",
    "AskRequest",
    "AnswerResponseConvSearch",
    "AnswerResponseChatGPT",
    "PromiseResponse",
    "ElicitationResponse",
    "FailureResponse",
    "AwaitRequest",
    "WhoResponse",
]
