# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Data models for conversation storage.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, List, Dict, Any
from nlweb_core.protocol.models import AskRequest, ResultObject


class ConversationMessage(BaseModel):
    """
    A complete conversation turn (user query + assistant response).

    This model stores both the user's request and the assistant's response
    in a single record, representing one complete interaction.
    """

    message_id: str = Field(
        ...,
        description="Unique identifier for this message exchange"
    )

    conversation_id: str = Field(
        ...,
        description="Identifier linking this message to a conversation"
    )

    timestamp: datetime = Field(
        ...,
        description="When this exchange was created"
    )

    # User's request - the complete v0.54 request
    request: AskRequest = Field(
        ...,
        description="Full v0.54 AskRequest from the user"
    )

    # Assistant's response - the result objects returned
    results: Optional[List[ResultObject]] = Field(
        None,
        description="Result objects returned by the assistant"
    )

    # Additional metadata
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional metadata (user_id, site, response_format, etc.)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message_id": "msg_123456",
                "conversation_id": "conv_abc123",
                "role": "user",
                "timestamp": "2025-01-15T10:30:00Z",
                "request": {
                    "query": {"text": "best pizza in Seattle"},
                    "prefer": {"streaming": True, "response_format": "conv_search"},
                },
                "metadata": {"site": "yelp.com"},
            }
        }
    )
