# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Generic provider caching and lazy loading infrastructure.

This module provides a reusable ProviderMap class that encapsulates the
double-checked locking pattern used for thread-safe lazy provider initialization.
"""

from typing import Generic, TypeVar, Callable, Any, Protocol, cast, runtime_checkable
import importlib
import logging
import threading

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
    Thread-safe lazy-loading cache for provider instances.

    This class encapsulates the common pattern of:
    1. Caching provider instances by name
    2. Using double-checked locking for thread safety
    3. Dynamically importing and instantiating providers from config

    Usage:
        _generative_providers: ProviderMap[GenerativeLLMProvider] = ProviderMap(
            config_getter=lambda name: get_config().get_generative_model_provider(name),
            error_prefix="Generative model provider",
        )

        # Get a provider (creates it lazily if needed)
        provider = _generative_providers.get("high")
    """

    def __init__(
        self,
        config_getter: Callable[[str], ProviderConfig | None],
        error_prefix: str,
    ):
        """
        Initialize a new ProviderMap.

        Args:
            config_getter: Callable that takes a provider name and returns its
                          configuration, or None if not configured.
            error_prefix: Prefix for error messages (e.g., "Generative model provider").
        """
        self._providers: dict[str, T] = {}
        self._lock = threading.Lock()
        self._config_getter = config_getter
        self._error_prefix = error_prefix

    def get(self, name: str) -> T:
        """
        Get a provider by name, creating it lazily if needed.

        Uses double-checked locking for thread-safe initialization.

        Args:
            name: The provider name to retrieve.

        Returns:
            The provider instance.

        Raises:
            ValueError: If the provider is not configured or cannot be loaded.
        """
        # Fast path: check without lock
        if name in self._providers:
            return self._providers[name]

        with self._lock:
            # Double-check after acquiring lock
            if name in self._providers:
                return self._providers[name]

            config = self._config_getter(name)

            if config is None:
                raise ValueError(f"{self._error_prefix} '{name}' is not configured")

            try:
                module = importlib.import_module(config.import_path)
                provider_class = getattr(module, config.class_name)
                provider = provider_class(**config.options)
                self._providers[name] = cast(T, provider)

                logger.debug(
                    f"Loaded {self._error_prefix.lower()} '{name}': {config.class_name}"
                )

            except (ImportError, AttributeError) as e:
                raise ValueError(
                    f"Failed to load {self._error_prefix.lower()} '{name}': {e}"
                )

            return self._providers[name]

    async def close(self) -> None:
        """Close all cached providers and clear the cache."""
        with self._lock:
            items = list(self._providers.items())
            self._providers.clear()

        for name, provider in items:
            try:
                await provider.close()
            except Exception as e:
                logger.warning(f"Error closing {self._error_prefix.lower()} '{name}': {e}")
