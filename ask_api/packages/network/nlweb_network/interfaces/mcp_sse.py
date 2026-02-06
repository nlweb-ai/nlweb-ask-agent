# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
MCP SSE interface - Model Context Protocol over Server-Sent Events.

Implements MCP protocol using Server-Sent Events for streaming responses.
This transport allows real-time streaming of tool execution results.
"""

import json
from typing import Any, Dict

from aiohttp import web
from nlweb_core.handler import AskHandler
from nlweb_core.protocol.models import AskRequest

from .base import BaseInterface


class MCPSSEInterface(BaseInterface):
    """
    MCP interface using Server-Sent Events transport.

    Handles MCP protocol methods with streaming support:
    - initialize: Protocol handshake (non-streaming)
    - tools/list: List available tools (non-streaming)
    - tools/call: Execute tool calls with streaming results (SSE)

    For tools/call, each result is streamed as it arrives via SSE.
    """

    MCP_VERSION = "2024-11-05"
    SERVER_NAME = "nlweb-mcp-server"
    SERVER_VERSION = "0.5.0"

    async def parse_request(self, request: web.Request) -> Dict[str, Any]:
        """
        Parse MCP request from query parameters (for SSE GET) or JSON body (for POST).

        Args:
            request: aiohttp Request object

        Returns:
            Dict containing 'method', 'params', 'id', and extracted 'query_params'

        Raises:
            ValueError: If request is invalid or malformed
        """
        # For SSE, we support both GET (query params) and POST (JSON body)
        if request.method == "POST":
            try:
                body = await request.json()
                method = body.get("method")
                params = body.get("params", {})
                request_id = body.get("id")
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON in request body")
        else:
            # GET request: extract from query params
            query_params = dict(request.query)
            method = query_params.get("method", "tools/call")
            request_id = query_params.get("id", "sse-1")
            params = {"name": "ask", "arguments": query_params}

        if not method:
            raise ValueError("Missing 'method' in request")

        return {
            "method": method,
            "params": params,
            "id": request_id,
            "query_params": (
                params.get("arguments", {}) if method == "tools/call" else {}
            ),
        }

    async def send_response(
        self, response: web.StreamResponse, data: Dict[str, Any]
    ) -> None:
        """
        Send MCP response as Server-Sent Event.

        Args:
            response: aiohttp StreamResponse object
            data: Data from NLWeb handler (dict with _meta or content)
        """
        # Wrap NLWeb data in MCP format
        # Each SSE event contains a JSON-RPC response with partial results
        mcp_data = {"jsonrpc": "2.0", "result": data}

        # Format as SSE: data: {json}\n\n
        event_data = f"data: {json.dumps(mcp_data)}\n\n"
        await response.write(event_data.encode("utf-8"))

    async def finalize_response(self, response: web.StreamResponse) -> None:
        """
        Close the SSE stream and send completion event.

        Args:
            response: aiohttp StreamResponse object
        """
        # Send final completion event
        completion_data = {
            "jsonrpc": "2.0",
            "result": {"_meta": {"nlweb/streaming_status": "finished"}},
        }
        event_data = f"data: {json.dumps(completion_data)}\n\n"
        await response.write(event_data.encode("utf-8"))
        await response.write_eof()

    def build_sse_json_response(self, request_id: Any, result: Dict[str, Any]) -> str:
        """
        Build SSE-formatted JSON-RPC response.

        Args:
            request_id: JSON-RPC request ID
            result: Result data

        Returns:
            SSE-formatted string
        """
        mcp_response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        return f"data: {json.dumps(mcp_response)}\n\n"

    def build_sse_error(self, request_id: Any, code: int, message: str) -> str:
        """
        Build SSE-formatted error response.

        Args:
            request_id: JSON-RPC request ID
            code: Error code
            message: Error message

        Returns:
            SSE-formatted error string
        """
        error_response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
        return f"data: {json.dumps(error_response)}\n\n"

    async def handle_request(
        self, request: web.Request, handler_class: type[AskHandler]
    ) -> web.Response:
        """
        Handle MCP request with SSE streaming.

        Args:
            request: aiohttp Request object
            handler_class: NLWeb handler class to instantiate (for tools/call)

        Returns:
            aiohttp Response (JSON for non-streaming, StreamResponse for streaming)
        """
        request_id = None

        try:
            # Parse MCP request
            parsed = await self.parse_request(request)
            method = parsed["method"]
            params = parsed["params"]
            request_id = parsed["id"]

            # Handle initialize (non-streaming)
            if method == "initialize":
                response_data = {
                    "protocolVersion": self.MCP_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": self.SERVER_NAME,
                        "version": self.SERVER_VERSION,
                    },
                }
                result = {"jsonrpc": "2.0", "id": request_id, "result": response_data}
                return web.json_response(result)

            # Handle tools/list (non-streaming)
            elif method == "tools/list":
                response_data = {
                    "tools": [
                        {
                            "name": "ask",
                            "description": "Search and answer natural language queries using NLWeb's vector database and LLM ranking",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "Natural language query",
                                    },
                                    "site": {
                                        "type": "string",
                                        "description": "Target site identifier",
                                    },
                                    "num_results": {
                                        "type": "integer",
                                        "description": "Number of results to return",
                                    },
                                },
                                "required": ["query"],
                            },
                        }
                    ]
                }
                result = {"jsonrpc": "2.0", "id": request_id, "result": response_data}
                return web.json_response(result)

            # Handle tools/call (streaming via SSE)
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                if tool_name != "ask":
                    error_msg = self.build_sse_error(
                        request_id, -32602, f"Unknown tool: {tool_name}"
                    )
                    response = web.StreamResponse(
                        status=200,
                        headers={
                            "Content-Type": "text/event-stream",
                            "Cache-Control": "no-cache",
                        },
                    )
                    await response.prepare(request)
                    await response.write(error_msg.encode("utf-8"))
                    await response.write_eof()
                    return response

                query_params = arguments

                if "query" not in query_params:
                    error_msg = self.build_sse_error(
                        request_id, -32602, "Missing required parameter: query"
                    )
                    response = web.StreamResponse(
                        status=200,
                        headers={
                            "Content-Type": "text/event-stream",
                            "Cache-Control": "no-cache",
                        },
                    )
                    await response.prepare(request)
                    await response.write(error_msg.encode("utf-8"))
                    await response.write_eof()
                    return response

                # Create SSE response
                response = web.StreamResponse(
                    status=200,
                    headers={
                        "Content-Type": "text/event-stream",
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                    },
                )
                await response.prepare(request)

                # Send initial metadata
                init_msg = self.build_sse_json_response(
                    request_id, {"_meta": {"version": "0.5"}}
                )
                await response.write(init_msg.encode("utf-8"))

                # MCP defaults to non-streaming
                if "streaming" not in query_params:
                    query_params["streaming"] = False

                # Build AskRequest from query_params
                ask_request = AskRequest.model_validate(query_params)

                # Create streaming output method
                output_method = self.create_output_method(response)

                # Create and run handler
                handler = handler_class()
                await handler.do(ask_request, output_method)

                # Finalize stream
                await self.finalize_response(response)

                return response

            else:
                error_msg = self.build_sse_error(
                    request_id, -32601, f"Method not found: {method}"
                )
                response = web.StreamResponse(
                    status=200,
                    headers={
                        "Content-Type": "text/event-stream",
                        "Cache-Control": "no-cache",
                    },
                )
                await response.prepare(request)
                await response.write(error_msg.encode("utf-8"))
                await response.write_eof()
                return response

        except Exception as e:
            error_msg = self.build_sse_error(
                request_id, -32603, f"Internal error: {str(e)}"
            )
            response = web.StreamResponse(
                status=200,
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                },
            )
            await response.prepare(request)
            await response.write(error_msg.encode("utf-8"))
            await response.write_eof()
            return response
