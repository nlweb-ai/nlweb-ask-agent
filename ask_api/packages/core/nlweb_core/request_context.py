# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Request context management using contextvars for tracking request IDs across async operations.
This allows correlating logs from different components for the same request.
"""

import contextvars
import uuid
import logging
from typing import Optional

# Context variable to store the current request ID
request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('request_id', default=None)


def set_request_id(request_id: Optional[str] = None) -> str:
    """
    Set the request ID for the current context.

    Args:
        request_id: Request ID to set. If None, generates a new UUID.

    Returns:
        The request ID that was set.
    """
    if request_id is None:
        request_id = str(uuid.uuid4())
    request_id_var.set(request_id)
    return request_id


def get_request_id() -> Optional[str]:
    """
    Get the request ID for the current context.

    Returns:
        The current request ID, or None if not set.
    """
    return request_id_var.get()


def clear_request_id():
    """Clear the request ID from the current context."""
    request_id_var.set(None)


class RequestIDFilter(logging.Filter):
    """
    Logging filter that adds request_id to log records.

    Usage:
        handler = logging.StreamHandler()
        handler.addFilter(RequestIDFilter())
        formatter = logging.Formatter('[%(request_id)s] %(levelname)s %(name)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    """

    def filter(self, record):
        """Add request_id to the log record."""
        record.request_id = get_request_id() or 'N/A'
        return True


def configure_logging_with_request_id():
    """
    Configure the root logger to include request IDs in all log messages.
    This should be called once at application startup.
    """
    # Get root logger
    root_logger = logging.getLogger()

    # Add RequestIDFilter to all handlers
    for handler in root_logger.handlers:
        handler.addFilter(RequestIDFilter())

        # Update formatter to include request_id if it doesn't already
        if handler.formatter:
            format_str = handler.formatter._fmt
            if format_str and 'request_id' not in format_str:
                # Prepend request_id to existing format
                new_format = '[%(request_id)s] ' + format_str
                handler.setFormatter(logging.Formatter(new_format))
