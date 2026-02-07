# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Pydantic models for query analysis LLM responses.

These models define the expected response structures for each query analysis type.
They are referenced by name in the XML configuration via the 'responseModel' attribute.
"""

from typing import Dict, List, Type

from pydantic import BaseModel, Field


class IrrelevantQueryResponse(BaseModel):
    """Response for detecting if site is irrelevant to query."""

    site_is_irrelevant_to_query: bool = Field(
        ..., description="True if the site is irrelevant to the query"
    )
    explanation_for_irrelevance: str = Field(
        default="", description="Explanation for why the site is irrelevant"
    )


class TransliterationResponse(BaseModel):
    """Response for transliteration (e.g., Hinglish to Devanagari)."""

    requires_transliteration: bool = Field(
        ..., description="True if the query needs transliteration"
    )
    transliterated_query: str = Field(
        ..., description="The transliterated query if needed, otherwise the original"
    )


class DecontextualizationResponse(BaseModel):
    """Response for query decontextualization with previous context."""

    requires_decontextualization: bool = Field(
        ..., description="True if the query needs decontextualization"
    )
    decontextualized_query: str = Field(
        ..., description="The rewritten query with context incorporated"
    )


class DecontextualizationWithRecencyResponse(BaseModel):
    """Response for query decontextualization with recency classification for news sites."""

    requires_decontextualization: bool = Field(
        ..., description="True if the query needs decontextualization"
    )
    decontextualized_query: str = Field(
        ..., description="The rewritten query with context incorporated"
    )
    is_seeking_recent_info: bool = Field(
        ...,
        description="True if the query is seeking recent/ongoing information about a general topic (e.g., 'Modi', 'Trump', 'weather'). False if asking about a specific completed event (e.g., 'Trump wins 2024 election', 'Modi's 2023 US visit')."
    )


class MemoryRequestResponse(BaseModel):
    """Response for detecting memory/remember requests."""

    is_memory_request: bool = Field(
        ..., description="True if user is asking to remember something"
    )
    memory_request: str = Field(
        default="", description="What the user is asking to remember"
    )


class QueryRewriteResponse(BaseModel):
    """Response for rewriting complex queries into simpler keyword queries."""

    rewritten_queries: List[str] = Field(
        ..., description="List of simplified keyword queries (1-5 queries)"
    )
    query_count: int = Field(..., description="Number of queries generated (1-5)")


class ItemTypesResponse(BaseModel):
    """Response for detecting multiple item types in a query."""

    item_types: str = Field(
        ..., description="List of item types being asked for, comma-separated"
    )
    item_queries: str = Field(
        ..., description="Separate queries for each item type, comma-separated"
    )


class ItemDetailResponse(BaseModel):
    """Response for detecting item detail queries vs list queries."""

    item_details_query: bool = Field(
        ..., description="True if asking for details of a specific item"
    )
    item_title: str = Field(default="", description="Title of the specific item")
    details_being_asked: str = Field(
        default="", description="What details the user is asking for"
    )


# Registry mapping model names to classes
# This allows XML to reference models by name string
RESPONSE_MODEL_REGISTRY: Dict[str, Type[BaseModel]] = {
    "IrrelevantQueryResponse": IrrelevantQueryResponse,
    "TransliterationResponse": TransliterationResponse,
    "DecontextualizationResponse": DecontextualizationResponse,
    "DecontextualizationWithRecencyResponse": DecontextualizationWithRecencyResponse,
    "MemoryRequestResponse": MemoryRequestResponse,
    "QueryRewriteResponse": QueryRewriteResponse,
    "ItemTypesResponse": ItemTypesResponse,
    "ItemDetailResponse": ItemDetailResponse,
}


def get_response_model(name: str) -> Type[BaseModel]:
    """
    Get a response model class by name.

    Args:
        name: The name of the response model (e.g., "DecontextualizationResponse")

    Returns:
        The Pydantic model class

    Raises:
        ValueError: If the model name is not found in the registry
    """
    if name not in RESPONSE_MODEL_REGISTRY:
        raise ValueError(
            f"Unknown response model: {name}. "
            f"Available models: {list(RESPONSE_MODEL_REGISTRY.keys())}"
        )
    return RESPONSE_MODEL_REGISTRY[name]
