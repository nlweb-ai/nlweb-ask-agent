# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Generic provider caching infrastructure.

This module provides a reusable ProviderMap class that eagerly instantiates
providers from a config dict at construction time.
"""

from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Generic, TypeVar, Any, Protocol, cast, runtime_checkable
import importlib
import logging

logger = logging.getLogger(__name__)


class ProviderConfig(Protocol):
    """Protocol for provider configuration objects."""

    import_path: str
    class_name: str
    options: dict[str, Any]


@runtime_checkable
class Closeable(Protocol):
    """Protocol for providers that can be closed."""

    async def close(self) -> None:
        """Close the provider and release resources."""
        ...


T = TypeVar("T", bound=Closeable)


class ProviderMap(Generic[T]):
    """
    Eagerly-initialized cache for provider instances.

    Accepts a dict of name → ProviderConfig, imports and instantiates every
    provider at construction time. No locks needed since all providers exist
    before any request arrives.

    Usage:
        _generative_providers: ProviderMap[GenerativeLLMProvider] = ProviderMap(
            config={"high": high_config, "low": low_config},
            error_prefix="Generative model provider",
        )

        provider = _generative_providers.get("high")
    """

    def __init__(
        self,
        config: Mapping[str, ProviderConfig],
        error_prefix: str,
    ):
        """
        Initialize a new ProviderMap, eagerly creating all providers.

        Args:
            config: Dict mapping provider names to their configurations.
            error_prefix: Prefix for error messages (e.g., "Generative model provider").

        Raises:
            ValueError: If any provider cannot be loaded.
        """
        self._providers: dict[str, T] = {}
        self._closed = False
        self._error_prefix = error_prefix
        self._name_overrides: ContextVar[dict[str, str]] = ContextVar(
            f"{error_prefix}_name_overrides"
        )

        for name, cfg in config.items():
            try:
                module = importlib.import_module(cfg.import_path)
                provider_class = getattr(module, cfg.class_name)
                self._providers[name] = cast(T, provider_class(**cfg.options))
                logger.debug(
                    f"Loaded {error_prefix.lower()} '{name}': {cfg.class_name}"
                )
            except (ImportError, AttributeError) as e:
                raise ValueError(
                    f"Failed to load {error_prefix.lower()} '{name}': {e}"
                )

    def get(self, name: str) -> T:
        """
        Get a provider by name, respecting any active name overrides.

        Args:
            name: The provider name to retrieve.

        Returns:
            The provider instance.

        Raises:
            RuntimeError: If providers have been shut down.
            ValueError: If the provider is not configured.
        """
        if self._closed:
            raise RuntimeError(f"{self._error_prefix} has been shut down")

        try:
            overrides = self._name_overrides.get()
            seen: set[str] = set()
            while name in overrides and name not in seen:
                seen.add(name)
                name = overrides[name]
        except LookupError:
            pass

        if name not in self._providers:
            raise ValueError(f"{self._error_prefix} '{name}' is not configured")

        return self._providers[name]

    @contextmanager
    def override(self, old_name: str, new_name: str):
        """Temporarily remap old_name -> new_name for provider lookups."""
        try:
            current = self._name_overrides.get()
        except LookupError:
            current = {}
        updated = {**current, old_name: new_name}
        token = self._name_overrides.set(updated)
        try:
            yield
        finally:
            self._name_overrides.reset(token)

    async def close(self) -> None:
        """Close all providers and mark as shut down."""
        self._closed = True
        for name, provider in self._providers.items():
            try:
                await provider.close()
            except Exception as e:
                logger.warning(f"Error closing {self._error_prefix.lower()} '{name}': {e}")
        self._providers.clear()
