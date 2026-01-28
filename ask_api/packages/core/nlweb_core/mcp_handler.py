# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
MCP Handler class

Implements MCP protocol using JSON-RPC 2.0 over standard HTTP.
"""

import json
from typing import Awaitable, Callable, Dict, Any
from nlweb_core.protocol.models import AskRequest

class MCPHandler:
    """
    MCP handler class

    Handles MCP protocol methods:
    - initialize: Protocol handshake
    - tools/list: List available tools
    - tools/call: Execute tool calls (routes to NLWeb handlers)

    This is the core MCP handling logic, returning responses in JSON-RPC 2.0 json.
    """

    MCP_VERSION = "2024-11-05"
    SERVER_NAME = "nlweb-mcp-server"
    SERVER_VERSION = "0.5.0"

    def __init__(self, nlweb_handler_class: Any):
        self.nlweb_handler_class = nlweb_handler_class
        self.responses = []

    def build_initialize_response(self, request_id: Any) -> Dict[str, Any]:
        """
        Build MCP initialize response.

        Args:
            request_id: JSON-RPC request ID

        Returns:
            JSON-RPC 2.0 response dict
        """
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": self.MCP_VERSION,
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": self.SERVER_NAME,
                    "version": self.SERVER_VERSION
                }
            }
        }

    def build_tools_list_response(self, request_id: Any) -> Dict[str, Any]:
        """
        Build MCP tools/list response.

        Args:
            request_id: JSON-RPC request ID

        Returns:
            JSON-RPC 2.0 response dict with available tools
        """
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": "ask",
                        "description": "Search and answer natural language queries using NLWeb's vector database and LLM ranking",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Natural language query"
                                },
                                "site": {
                                    "type": "string",
                                    "description": "Target site identifier"
                                },
                                "num_results": {
                                    "type": "integer",
                                    "description": "Number of results to return"
                                },
                                "streaming": {
                                    "type": "boolean",
                                    "description": "Enable streaming response",
                                    "default": False
                                }
                            },
                            "required": ["query"]
                        }
                    }
                ]
            }
        }

    def build_tool_call_response(self, request_id: Any, nlweb_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build MCP tools/call response from NLWeb result.

        Args:
            request_id: JSON-RPC request ID
            nlweb_result: Result from NLWeb handler

        Returns:
            JSON-RPC 2.0 response dict
        """
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(nlweb_result, indent=2)
                    }
                ]
            }
        }

    def build_error_response(self, request_id: Any, code: int, message: str) -> Dict[str, Any]:
        """
        Build JSON-RPC 2.0 error response.

        Args:
            request_id: JSON-RPC request ID
            code: Error code (JSON-RPC standard codes)
            message: Error message

        Returns:
            JSON-RPC 2.0 error response dict
        """
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message
            }
        }

    def build_json_response(self, responses: list) -> Dict[str, Any]:
        """
        Build final JSON response from collected outputs.

        Args:
            responses: List of response dicts from handler

        Returns:
            Complete JSON response dict
        """
        # Separate _meta and content items
        meta = {}
        content = []

        for response in responses:
            if '_meta' in response:
                # Merge meta information (first one wins for duplicates)
                for key, value in response['_meta'].items():
                    if key not in meta:
                        meta[key] = value
            if 'content' in response:
                # Collect all content items
                content.extend(response['content'])

        # Build final response
        result = {}
        if meta:
            result['_meta'] = meta
        if content:
            result['content'] = content

        return result

    async def handle_request(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle MCP JSON-RPC 2.0 request.

        Args:
            parsed: Parsed JSON-RPC 2.0 request

        Returns:
            JSON response with JSON-RPC 2.0 format
        """
        request_id = None

        try:
            # Parse MCP request
            method = parsed["method"]
            params = parsed.get("params", {})
            request_id = parsed.get("id", None)

            # Handle initialize
            if method == "initialize":
                return self.build_initialize_response(request_id)

            # Handle tools/list
            elif method == "tools/list":
                return self.build_tools_list_response(request_id)

            # Handle tools/call
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                if tool_name != "ask":
                    response = self.build_error_response(
                        request_id,
                        -32602,
                        f"Unknown tool: {tool_name}"
                    )
                    return response

                # MCP calls default to non-streaming
                if "streaming" not in arguments:
                    arguments["streaming"] = False

                query_params = arguments

                if 'query' not in query_params:
                    response = self.build_error_response(
                        request_id,
                        -32602,
                        "Missing required parameter: query"
                    )
                    return response

                # Build AskRequest from query_params
                ask_request = AskRequest.from_query_params(query_params)

                # Create collector output method
                output_method = self.create_collector_output_method()

                # Create and run handler
                handler = self.nlweb_handler_class(ask_request, output_method)
                await handler.runQuery()

                # Build NLWeb result from collected responses
                nlweb_result = self.build_json_response(self.get_collected_responses())

                # Wrap in MCP response
                response = self.build_tool_call_response(request_id, nlweb_result)
                return response

            else:
                response = self.build_error_response(
                    request_id,
                    -32601,
                    f"Method not found: {method}"
                )
                return response

        except ValueError as e:
            response = self.build_error_response(
                request_id,
                -32700 if "JSON" in str(e) else -32602,
                str(e)
            )
            return response

        except Exception as e:
            response = self.build_error_response(
                request_id,
                -32603,
                f"Internal error: {str(e)}"
            )
            return response

    def create_collector_output_method(self) -> Callable[[Dict[str, Any]], Awaitable[None]]:
        async def output_method(data: Dict[str, Any]) -> None:
            self.responses.append(data)

        return output_method

    def get_collected_responses(self) -> list:
        responses = self.responses
        self.responses = []
        return responses
