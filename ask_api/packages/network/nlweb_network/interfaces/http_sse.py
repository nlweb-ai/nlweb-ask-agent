# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
HTTP SSE interface - Streaming HTTP responses via Server-Sent Events.

Handles both GET and POST requests, streams results as they arrive
using the SSE (Server-Sent Events) protocol.
"""

import json
import logging
from typing import Dict, Any
from aiohttp import web
from .base import BaseInterface
from nlweb_core.protocol.models import AskRequest

logger = logging.getLogger(__name__)


class HTTPSSEInterface(BaseInterface):
    """
    HTTP interface that streams responses via Server-Sent Events (streaming=true).

    Supports both GET and POST methods:
    - GET: Parameters from query string
    - POST: Parameters from JSON body (takes precedence) or query string

    Streams each result immediately as it's generated.
    """

    async def send_response(
        self, response: web.StreamResponse, data: Dict[str, Any]
    ) -> None:
        """
        Send data as Server-Sent Event.

        Args:
            response: aiohttp StreamResponse object
            data: Data from NLWeb handler (dict with _meta or content)
        """
        # Format as SSE: data: {json}\n\n
        event_data = f"data: {json.dumps(data)}\n\n"
        await response.write(event_data.encode("utf-8"))

    async def finalize_response(self, response: web.StreamResponse) -> None:
        """
        Close the SSE stream.

        Args:
            response: aiohttp StreamResponse object
        """
        await response.write_eof()

    async def handle_request(
        self, request: web.Request, handler_class
    ) -> web.StreamResponse:
        """
        Handle HTTP request and stream SSE responses.

        Args:
            request: aiohttp Request object
            handler_class: NLWeb handler class to instantiate

        Returns:
            aiohttp StreamResponse
        """
        import sys

        try:
            # Build AskRequest from query_params
            body = await request.json()
            ask_request = AskRequest.model_validate(body)

            # Create SSE response
            response = web.StreamResponse(
                status=200,
                reason="OK",
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )
            await response.prepare(request)

            # Create streaming output method
            output_method = self.create_output_method(response)

            # Create and run handler
            handler = handler_class(ask_request, output_method)
            await handler.runQuery()

            # Finalize stream
            await self.finalize_response(response)

            return response

        except ValueError as e:
            logger.error(f"ValueError: {e}", exc_info=True)
            import traceback

            traceback.print_exc(file=sys.stderr)
            # For errors, return v0.54 Failure response via SSE
            response = web.StreamResponse(
                status=200,  # SSE uses 200 even for errors
                reason="OK",
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                },
            )
            await response.prepare(request)

            # Send _meta
            meta_data = {"_meta": {"response_type": "Failure", "version": "0.54"}}
            await response.write(f"data: {json.dumps(meta_data)}\n\n".encode("utf-8"))

            # Send error
            error_data = {"error": {"code": "INVALID_REQUEST", "message": str(e)}}
            await response.write(f"data: {json.dumps(error_data)}\n\n".encode("utf-8"))
            await response.write_eof()

            return response

        except Exception as e:
            logger.error(f"Unexpected exception: {e}", exc_info=True)
            import traceback

            traceback.print_exc(file=sys.stderr)
            # For unexpected errors, return v0.54 Failure response via SSE
            response = web.StreamResponse(
                status=200,
                reason="OK",
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                },
            )
            await response.prepare(request)

            # Send _meta
            meta_data = {"_meta": {"response_type": "Failure", "version": "0.54"}}
            await response.write(f"data: {json.dumps(meta_data)}\n\n".encode("utf-8"))

            # Send error
            error_data = {"error": {"code": "INTERNAL_ERROR", "message": str(e)}}
            await response.write(f"data: {json.dumps(error_data)}\n\n".encode("utf-8"))
            await response.write_eof()

            return response
