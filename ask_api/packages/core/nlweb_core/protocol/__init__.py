"""
NLWeb Protocol Data Models

These models define the data contracts for the NLWeb protocol.
Generated from TypeSpec specification at: https://github.com/nlweb-ai/nlweb-typespec

DO NOT EDIT models.py directly - regenerate from TypeSpec instead.
"""

from .models import (
    Agent,
    AnswerResponseChatGPT,
    AnswerResponseConvSearch,
    AskRequest,
    AskResponseMeta,
    AwaitRequest,
    ClientType,
    Context,
    ElicitationResponse,
    FailureResponse,
    Meta,
    Prefer,
    PromiseResponse,
    Query,
    Resource,
    ResourceContent,
    ResponseType,
    ReturnResponse,
    TextContent,
    WhoRequest,
    WhoResponse,
    WhoResponseMeta,
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
