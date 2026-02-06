# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
A2A (Agent2Agent) interface using Server-Sent Events for streaming.

This module implements the A2A protocol for agent-to-agent communication using
SSE for streaming responses. It supports the message/stream method for streaming
task execution with progressive updates.
"""

import json
from typing import Any, Dict

from aiohttp import web
from nlweb_core.handler import AskHandler
from nlweb_core.protocol.models import AskRequest

from .base import BaseInterface


class A2ASSEInterface(BaseInterface):
    """A2A interface using Server-Sent Events for streaming."""

    A2A_VERSION = "0.2.6"
    AGENT_NAME = "nlweb-a2a-agent"
    AGENT_VERSION = "0.5.0"

    async def parse_request(self, request: web.Request) -> Dict[str, Any]:
        """
        Parse A2A JSON-RPC 2.0 request for streaming.

        Expected format:
        {
            "jsonrpc": "2.0",
            "id": <request_id>,
            "method": "message/stream",
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

    async def send_response(
        self, response: web.StreamResponse, data: Dict[str, Any]
    ) -> None:
        """
        Send data through SSE stream in A2A format.

        Each SSE event contains a JSON-RPC 2.0 result with A2A message parts.
        """
        # Check if this is NLWeb internal data
        if "content" in data:
            # Convert NLWeb content to A2A message parts
            parts = []

            for item in data["content"]:
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

            # Wrap in A2A message format
            a2a_data = {
                "jsonrpc": "2.0",
                "result": {
                    "message": {"role": "agent", "parts": parts},
                    "status": "working",
                },
            }

        elif "_meta" in data:
            # Handle metadata
            if data["_meta"].get("nlweb/streaming_status") == "finished":
                # Final completion message
                a2a_data = {"jsonrpc": "2.0", "result": {"status": "completed"}}
            else:
                # Initial metadata
                a2a_data = {
                    "jsonrpc": "2.0",
                    "result": {
                        "message": {
                            "role": "agent",
                            "parts": [
                                {
                                    "kind": "text",
                                    "text": f"Search started. Version: {data['_meta'].get('version', 'unknown')}",
                                }
                            ],
                        },
                        "status": "working",
                    },
                }
        else:
            # Pass through as-is if already in A2A format
            a2a_data = data

        # Format as SSE
        event_data = f"data: {json.dumps(a2a_data)}\n\n"
        await response.write(event_data.encode("utf-8"))

    async def finalize_response(self, response: web.StreamResponse) -> None:
        """
        Finalize the SSE stream with completion status.
        """
        # Send final completion event
        completion_data = {"jsonrpc": "2.0", "result": {"status": "completed"}}
        event_data = f"data: {json.dumps(completion_data)}\n\n"
        await response.write(event_data.encode("utf-8"))
        await response.write_eof()

    async def handle_request(
        self, request: web.Request, handler_class: type[AskHandler]
    ) -> web.StreamResponse:
        """
        Handle A2A SSE streaming request.

        Supports message/stream for progressive result streaming.
        """
        try:
            parsed = await self.parse_request(request)
        except Exception as e:
            # For SSE, send error as first event then close
            response = web.StreamResponse(
                status=200,
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )
            await response.prepare(request)

            error_data = {
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": f"Parse error: {str(e)}"},
            }
            event_data = f"data: {json.dumps(error_data)}\n\n"
            await response.write(event_data.encode("utf-8"))
            await response.write_eof()
            return response

        method = parsed["method"]
        query = parsed.get("query")

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

        # Handle message/stream request
        if method == "message/stream":
            if not query:
                error_data = {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32602,
                        "message": "Missing query in message parts",
                    },
                }
                event_data = f"data: {json.dumps(error_data)}\n\n"
                await response.write(event_data.encode("utf-8"))
                await response.write_eof()
                return response

            try:
                # Execute NLWeb handler in streaming mode
                query_params = parsed["query_params"]
                query_params["streaming"] = True  # Force streaming for message/stream

                # Build AskRequest from query_params
                ask_request = AskRequest.model_validate(query_params)

                output_method = self.create_output_method(response)
                handler = handler_class()
                await handler.do(ask_request, output_method)

                # Finalize response
                await self.finalize_response(response)
                return response

            except Exception as e:
                error_data = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
                }
                event_data = f"data: {json.dumps(error_data)}\n\n"
                await response.write(event_data.encode("utf-8"))
                await response.write_eof()
                return response

        else:
            # Unknown method
            error_data = {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
            event_data = f"data: {json.dumps(error_data)}\n\n"
            await response.write(event_data.encode("utf-8"))
            await response.write_eof()
            return response
