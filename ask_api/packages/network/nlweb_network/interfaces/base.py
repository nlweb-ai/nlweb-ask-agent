# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Base interface class for all NLWeb network transports.

All transport adapters (HTTP, MCP, A2A) inherit from this base class.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Callable, Awaitable


class BaseInterface(ABC):
    """
    Abstract base class for NLWeb network interfaces.

    Each interface adapter converts protocol-specific requests into
    a common format that NLWeb handlers can process, and converts
    NLWeb outputs back into the appropriate protocol format.
    """

    def __init__(self):
        """Initialize the interface."""
        self.responses = []

    @abstractmethod
    async def parse_request(self, request: Any) -> Dict[str, Any]:
        """
        Parse incoming request and extract query parameters.

        Args:
            request: Protocol-specific request object

        Returns:
            Dict of query parameters for NLWeb handler

        Raises:
            ValueError: If request is invalid or missing required fields
        """
        pass

    @abstractmethod
    async def send_response(self, response: Any, data: Dict[str, Any]) -> None:
        """
        Send data through the protocol-specific response object.

        Args:
            response: Protocol-specific response object (e.g., web.Response, StreamWriter)
            data: Data to send (dict from NLWeb handler output_method)
        """
        pass

    @abstractmethod
    async def finalize_response(self, response: Any) -> None:
        """
        Finalize and close the response stream.

        Args:
            response: Protocol-specific response object
        """
        pass

    def create_output_method(self, response: Any) -> Callable[[Dict[str, Any]], Awaitable[None]]:
        """
        Create an output_method callback for NLWeb handlers.

        This method returns an async function that will be called by the
        NLWeb handler with each piece of output data. The callback formats
        and sends the data according to the protocol.

        Args:
            response: Protocol-specific response object

        Returns:
            Async callback function for handler output
        """
        async def output_method(data: Dict[str, Any]) -> None:
            """Callback for handler output."""
            await self.send_response(response, data)

        return output_method

    def create_collector_output_method(self) -> Callable[[Dict[str, Any]], Awaitable[None]]:
        """
        Create an output_method that collects responses instead of streaming.

        Used for non-streaming modes where all responses are collected
        and returned as a single response.

        Returns:
            Async callback function that collects outputs
        """
        async def output_method(data: Dict[str, Any]) -> None:
            """Callback that collects output."""
            self.responses.append(data)

        return output_method

    def get_collected_responses(self) -> list:
        """
        Get all collected responses and clear the buffer.

        Returns:
            List of collected response dicts
        """
        responses = self.responses
        self.responses = []
        return responses
