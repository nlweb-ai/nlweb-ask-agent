# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Conversation storage module for NLWeb.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

from nlweb_core.conversation.models import ConversationMessage
from nlweb_core.conversation.storage import (
    ConversationStorageInterface,
    ConversationStorageClient
)

__all__ = [
    'ConversationMessage',
    'ConversationStorageInterface',
    'ConversationStorageClient'
]
