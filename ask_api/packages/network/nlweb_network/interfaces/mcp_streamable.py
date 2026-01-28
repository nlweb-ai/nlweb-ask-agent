# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
MCP StreamableHTTP interface - Model Context Protocol over HTTP.

Implements MCP protocol using JSON-RPC 2.0 over standard HTTP.
This is the recommended MCP transport for HTTP-based communication.
"""

import json
from typing import Dict, Any
from aiohttp import web
from .base import BaseInterface
from nlweb_core.mcp_handler import MCPHandler

class MCPStreamableInterface(BaseInterface):
    """
    MCP interface using StreamableHTTP transport (JSON-RPC 2.0 over HTTP).

    Handles MCP protocol methods:
    - initialize: Protocol handshake
    - tools/list: List available tools
    - tools/call: Execute tool calls (routes to NLWeb handlers)

    MCP calls default to non-streaming mode.
    """

    MCP_VERSION = "2024-11-05"
    SERVER_NAME = "nlweb-mcp-server"
    SERVER_VERSION = "0.5.0"

    async def parse_request(self, request: web.Request) -> Dict[str, Any]:
        """
        Parse MCP JSON-RPC 2.0 request.

        Args:
            request: aiohttp Request object with JSON-RPC body

        Returns:
            Dict containing 'method', 'params', 'id', and extracted 'query_params'

        Raises:
            ValueError: If request is invalid or malformed
        """
        try:
            body = await request.json()
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON in request body")

        # MCP uses JSON-RPC 2.0 format
        method = body.get("method")
        params = body.get("params", {})
        request_id = body.get("id")

        if not method:
            raise ValueError("Missing 'method' in JSON-RPC request")

        return {
            "method": method,
            "params": params,
            "id": request_id,
            "query_params": params.get("arguments", {}) if method == "tools/call" else {}
        }

    async def handle_request(self, request: web.Request, handler_class) -> web.Response:
        """
        Handle MCP JSON-RPC 2.0 request.

        Args:
            request: aiohttp Request object
            handler_class: NLWeb handler class to instantiate (for tools/call)

        Returns:
            aiohttp JSON response with JSON-RPC 2.0 format
        """
        request_id = None
        try:
            # Parse MCP request
            parsed = await self.parse_request(request)
            request_id = parsed.get("id", None)

            mcp = MCPHandler(handler_class)
            response = await mcp.handle_request(parsed)
            return web.json_response(response)
        except Exception as e:
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }
            return web.json_response(response, status=500)

    async def send_response(self, response: web.Response, data: Dict[str, Any]) -> None:
        """
        Not used for MCP StreamableHTTP (uses single JSON-RPC response).

        Args:
            response: Not used
            data: Not used
        """
        pass

    async def finalize_response(self, response: web.Response) -> None:
        """
        Not used for MCP StreamableHTTP.

        Args:
            response: Not used
        """
        pass
