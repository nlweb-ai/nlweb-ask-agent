# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""Pytest configuration and fixtures for core package tests."""

import pytest
from nlweb_core.config import _STATIC_CONFIG, initialize_config


@pytest.fixture(scope="session", autouse=True)
def init_config():
    """Initialize configuration before any tests run."""
    global _STATIC_CONFIG
    # Only initialize if not already initialized
    import nlweb_core.config as config_module

    if config_module._STATIC_CONFIG is None:
        initialize_config()
