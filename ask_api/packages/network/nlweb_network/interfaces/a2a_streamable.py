# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
A2A (Agent2Agent) interface using StreamableHTTP (JSON-RPC 2.0 over HTTP).

This module implements the A2A protocol for agent-to-agent communication using
standard HTTP with JSON-RPC 2.0 message format. It supports the message/send method
for synchronous request/response interactions.
"""

import json
from typing import Any, Dict

from aiohttp import web
from nlweb_core.handler import AskHandler
from nlweb_core.protocol.models import AskRequest

from .base import BaseInterface


class A2AStreamableInterface(BaseInterface):
    """A2A interface using StreamableHTTP (JSON-RPC 2.0 over HTTP)."""

    A2A_VERSION = "0.2.6"
    AGENT_NAME = "nlweb-a2a-agent"
    AGENT_VERSION = "0.5.0"

    async def parse_request(self, request: web.Request) -> Dict[str, Any]:
        """
        Parse A2A JSON-RPC 2.0 request.

        Expected format:
        {
            "jsonrpc": "2.0",
            "id": <request_id>,
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "<query>"}]
                }
            }
        }
        """
        body = await request.json()

        method = body.get("method")
        params = body.get("params", {})
        request_id = body.get("id")

        # Extract query from message parts
        query = None
        message = params.get("message", {})
        parts = message.get("parts", [])
        for part in parts:
            if part.get("kind") == "text":
                query = part.get("text")
                break

        return {
            "method": method,
            "params": params,
            "id": request_id,
            "query": query,
            "query_params": {"query": query} if query else {},
        }

    def build_agent_card_response(self, request_id: Any) -> Dict[str, Any]:
        """
        Build A2A agent card response (agent discovery).

        Returns agent metadata including capabilities, skills, and endpoints.
        """
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "agentCard": {
                    "version": self.A2A_VERSION,
                    "agent": {
                        "name": self.AGENT_NAME,
                        "version": self.AGENT_VERSION,
                        "description": "NLWeb RAG agent for natural language search and retrieval",
                    },
                    "capabilities": {
                        "streaming": True,
                        "taskManagement": False,
                        "multiTurn": False,
                    },
                    "skills": [
                        {
                            "name": "search",
                            "description": "Search and retrieve relevant information using natural language queries with RAG pipeline",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "Natural language search query",
                                    },
                                    "site": {
                                        "type": "string",
                                        "description": "Target site identifier (optional)",
                                    },
                                    "num_results": {
                                        "type": "integer",
                                        "description": "Number of results to return (optional)",
                                    },
                                },
                                "required": ["query"],
                            },
                        }
                    ],
                    "transports": [
                        {"type": "http", "url": "/a2a", "protocol": "json-rpc-2.0"},
                        {"type": "sse", "url": "/a2a-sse", "protocol": "json-rpc-2.0"},
                    ],
                }
            },
        }

    def build_message_response(
        self, request_id: Any, responses: list
    ) -> Dict[str, Any]:
        """
        Build A2A message/send response with NLWeb results.

        Wraps NLWeb RAG results in A2A message format.
        """
        # Combine all NLWeb responses
        content_items = []
        meta = {}

        for response in responses:
            if "_meta" in response:
                for key, value in response["_meta"].items():
                    if key not in meta:
                        meta[key] = value
            if "content" in response:
                content_items.extend(response["content"])

        # Convert NLWeb content to A2A message parts
        parts = []

        # Add metadata as text part
        if meta:
            meta_text = f"Search completed successfully. Version: {meta.get('version', 'unknown')}"
            parts.append({"kind": "text", "text": meta_text})

        # Add each content item
        for item in content_items:
            # Add description as text
            if "description" in item:
                parts.append({"kind": "text", "text": item["description"]})

            # Add structured data as artifact
            parts.append(
                {
                    "kind": "artifact",
                    "artifact": {
                        "name": item.get("name", "result"),
                        "mimeType": "application/json",
                        "data": json.dumps(item),
                    },
                }
            )

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "message": {"role": "agent", "parts": parts},
                "status": "completed",
            },
        }

    def build_error_response(
        self, request_id: Any, error_message: str, error_code: int = -32603
    ) -> Dict[str, Any]:
        """
        Build A2A JSON-RPC 2.0 error response.

        Error codes:
        -32700: Parse error
        -32600: Invalid request
        -32601: Method not found
        -32602: Invalid params
        -32603: Internal error
        """
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": error_code, "message": error_message},
        }

    async def send_response(self, response: Any, data: Dict[str, Any]) -> None:
        """
        Not used for StreamableHTTP - responses are sent directly as JSON.
        """
        pass

    async def finalize_response(self, response: Any) -> None:
        """
        Not used for StreamableHTTP - responses are sent directly as JSON.
        """
        pass

    async def handle_request(
        self, request: web.Request, handler_class: type[AskHandler]
    ) -> web.Response:
        """
        Handle A2A StreamableHTTP request.

        Supports:
        - agent/card (agent discovery)
        - message/send (synchronous search)
        """
        try:
            parsed = await self.parse_request(request)
        except Exception as e:
            error_response = self.build_error_response(
                None, f"Parse error: {str(e)}", -32700
            )
            return web.json_response(error_response, status=400)

        method = parsed["method"]
        request_id = parsed["id"]

        # Handle agent card request
        if method == "agent/card":
            response = self.build_agent_card_response(request_id)
            return web.json_response(response)

        # Handle message/send request
        elif method == "message/send":
            query = parsed.get("query")

            if not query:
                error_response = self.build_error_response(
                    request_id, "Missing query in message parts", -32602
                )
                return web.json_response(error_response, status=400)

            try:
                # Execute NLWeb handler in non-streaming mode
                query_params = parsed["query_params"]
                query_params["streaming"] = (
                    False  # Force non-streaming for message/send
                )

                # Build AskRequest from query_params
                ask_request = AskRequest.model_validate(query_params)

                output_method = self.create_collector_output_method()
                handler = handler_class()
                await handler.do(ask_request, output_method)

                # Get collected responses
                responses = self.get_collected_responses()

                # Build A2A response
                response = self.build_message_response(request_id, responses)
                return web.json_response(response)

            except Exception as e:
                error_response = self.build_error_response(
                    request_id, f"Internal error: {str(e)}", -32603
                )
                return web.json_response(error_response, status=500)

        else:
            # Unknown method
            error_response = self.build_error_response(
                request_id, f"Method not found: {method}", -32601
            )
            return web.json_response(error_response, status=404)
