# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
HTTP JSON interface - Non-streaming HTTP responses.

Handles both GET and POST requests, collects all results,
and returns a single JSON response.
"""

import json
import logging
from typing import Dict, Any
from aiohttp import web
from .base import BaseInterface
from nlweb_core.protocol.models import AskRequest

logger = logging.getLogger(__name__)


class HTTPJSONInterface(BaseInterface):
    """
    HTTP interface that returns complete JSON responses (streaming=false).

    Supports POST methods:
    - POST: Parameters from JSON body (takes precedence) or query string
    """

    async def send_response(self, response: web.Response, data: Dict[str, Any]) -> None:
        """
        Collect response data (not sent immediately in non-streaming mode).

        Args:
            response: Not used in non-streaming mode
            data: Data from NLWeb handler
        """
        # Data is collected via create_collector_output_method
        # This method is not used in non-streaming mode
        pass

    async def finalize_response(self, response: web.Response) -> None:
        """
        Not used in non-streaming mode (response created and returned directly).

        Args:
            response: Not used
        """
        pass

    def build_json_response(self, responses: list) -> Dict[str, Any]:
        """
        Build final JSON response from collected outputs.
        Constructs v0.54 compliant response.

        Args:
            responses: List of response dicts from handler

        Returns:
            Complete JSON response dict in v0.54 format
        """
        # Collect _meta and content
        meta = None
        results = []
        elicitation = None
        promise = None
        error = None

        for response in responses:
            if "_meta" in response:
                meta = response["_meta"]
            if "results" in response:
                results.extend(response["results"])
            if "elicitation" in response:
                elicitation = response["elicitation"]
            if "promise" in response:
                promise = response["promise"]
            if "error" in response:
                error = response["error"]

        # Ensure required meta fields
        if not meta:
            meta = {"response_type": "Answer", "version": "0.54"}
        if "response_type" not in meta:
            meta["response_type"] = "Answer"
        if "version" not in meta:
            meta["version"] = "0.54"

        # Build response based on response_type
        response_type = meta["response_type"]

        if response_type == "Answer":
            return {"_meta": meta, "results": results}
        elif response_type == "Elicitation":
            if not elicitation:
                raise ValueError("Elicitation response missing elicitation object")
            return {"_meta": meta, "elicitation": elicitation}
        elif response_type == "Promise":
            if not promise:
                raise ValueError("Promise response missing promise object")
            return {"_meta": meta, "promise": promise}
        elif response_type == "Failure":
            if not error:
                raise ValueError("Failure response missing error object")
            return {"_meta": meta, "error": error}
        else:
            raise ValueError(f"Unknown response_type: {response_type}")

    async def handle_request(self, request: web.Request, handler_class) -> web.Response:
        """
        Handle complete HTTP request and return JSON response.

        Args:
            request: aiohttp Request object
            handler_class: NLWeb handler class to instantiate

        Returns:
            aiohttp JSON response
        """
        try:
            # Parse request
            body = await request.json()

            # Build AskRequest from body
            ask_request = AskRequest.model_validate(body)

            # Create collector output method
            output_method = self.create_collector_output_method()

            # Create and run handler
            handler = handler_class(ask_request, output_method)
            await handler.runQuery()

            # Build and return JSON response
            responses = self.get_collected_responses()
            result = self.build_json_response(responses)

            return web.json_response(result)

        except ValueError as e:
            logger.error(f"[ERROR] ValueError: {e}", exc_info=True)
            return web.json_response(
                {
                    "_meta": {"response_type": "Failure", "version": "0.54"},
                    "error": {"code": "INVALID_REQUEST", "message": str(e)},
                },
                status=400,
            )
        except Exception as e:
            logger.error(f"[ERROR] ValueError: {e}", exc_info=True)
            return web.json_response(
                {
                    "_meta": {"response_type": "Failure", "version": "0.54"},
                    "error": {"code": "INTERNAL_ERROR", "message": str(e)},
                },
                status=500,
            )
