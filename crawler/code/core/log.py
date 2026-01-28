"""
You can change the log level of the master or worker processes by setting
the `LOG_LEVEL` and `LOG_LEVEL_AZURE` environment variables.

Generally, you don't need to set these unless you are debugging.
"""

import logging
import time


def level(env):
    """
    Args:
        env: dict-like object.
    Returns:
        One of the log levels from `logging`.
    """
    level = env.get("LOG_LEVEL", "INFO").upper()
    match level:
        case "DEBUG":
            return logging.DEBUG
        case "INFO":
            return logging.INFO
        case "WARNING":
            return logging.WARNING
        case "ERROR":
            return logging.ERROR
        case "CRITICAL":
            return logging.CRITICAL
        case _:
            return logging.INFO


def level_azure(env):
    """
    Args:
        env: dict-like object.
    Returns:
        One of the log levels from `logging` for Azure SDK logs.
    """
    level = env.get("LOG_LEVEL_AZURE", "WARNING").upper()
    match level:
        case "DEBUG":
            return logging.DEBUG
        case "INFO":
            return logging.INFO
        case "WARNING":
            return logging.WARNING
        case "ERROR":
            return logging.ERROR
        case "CRITICAL":
            return logging.CRITICAL
        case _:
            return logging.WARNING


def configure(environ):
    """Configure logging using environment variables."""
    logging.basicConfig(
        level=level(environ),
        format="%(asctime)s.%(msecs)03dZ\t[%(name)s]\t%(levelname)s:\t%(message)s",
        # ISO 8601 format with UTC 'Z' suffix
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    logging.Formatter.converter = time.gmtime

    # Azure SDK logs are very verbose.
    azure_logger = logging.getLogger("azure")
    azure_logger.setLevel(level_azure(environ))
