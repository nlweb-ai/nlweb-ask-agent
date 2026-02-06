"""NLWeb Network Interfaces - Protocol adapters for different transports."""

from .a2a_sse import A2ASSEInterface
from .a2a_streamable import A2AStreamableInterface
from .base import BaseInterface
from .http_json import HTTPJSONInterface
from .http_sse import HTTPSSEInterface
from .mcp_sse import MCPSSEInterface
from .mcp_streamable import MCPStreamableInterface

__all__ = [
    "BaseInterface",
    "HTTPJSONInterface",
    "HTTPSSEInterface",
    "MCPSSEInterface",
    "MCPStreamableInterface",
    "A2ASSEInterface",
    "A2AStreamableInterface",
]
