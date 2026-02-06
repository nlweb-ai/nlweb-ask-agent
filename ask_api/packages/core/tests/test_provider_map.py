# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""Tests for ProviderMap provider caching and name override infrastructure."""

from dataclasses import dataclass, field

import pytest
from nlweb_core.provider_map import ProviderMap

# -- Test fixtures -----------------------------------------------------------


class FakeProvider:
    """Minimal provider satisfying the Closeable protocol."""

    def __init__(self, **options):
        self.options = options
        self.closed = False

    async def close(self):
        self.closed = True


def _make_map(**names: dict) -> ProviderMap:
    """Build a ProviderMap with named FakeProviders, bypassing import machinery."""
    pm = ProviderMap(config={}, error_prefix="Test provider")
    for name, opts in names.items():
        pm._providers[name] = FakeProvider(**opts)
    return pm


# -- Basic get / error tests -------------------------------------------------


class TestProviderMapGet:
    def test_get_returns_correct_provider(self):
        pm = _make_map(alpha={"x": 1}, beta={"x": 2})
        assert pm.get("alpha").options == {"x": 1}
        assert pm.get("beta").options == {"x": 2}

    def test_get_unknown_name_raises(self):
        pm = _make_map(alpha={})
        with pytest.raises(ValueError, match="'missing' is not configured"):
            pm.get("missing")

    @pytest.mark.asyncio
    async def test_get_after_close_raises(self):
        pm = _make_map(alpha={})
        await pm.close()
        with pytest.raises(RuntimeError, match="has been shut down"):
            pm.get("alpha")

    @pytest.mark.asyncio
    async def test_close_calls_provider_close(self):
        pm = _make_map(alpha={}, beta={})
        alpha = pm.get("alpha")
        beta = pm.get("beta")
        await pm.close()
        assert alpha.closed
        assert beta.closed

    def test_bad_import_path_raises(self):
        @dataclass
        class BadConfig:
            import_path: str = "no.such.module"
            class_name: str = "Foo"
            options: dict = field(default_factory=dict)

        with pytest.raises(ValueError, match="Failed to load"):
            ProviderMap(config={"bad": BadConfig()}, error_prefix="Test provider")

    def test_bad_class_name_raises(self):
        @dataclass
        class BadConfig:
            import_path: str = "os"
            class_name: str = "NoSuchClass"
            options: dict = field(default_factory=dict)

        with pytest.raises(ValueError, match="Failed to load"):
            ProviderMap(config={"bad": BadConfig()}, error_prefix="Test provider")


# -- Override context manager tests ------------------------------------------


class TestProviderMapOverride:
    def test_override_remaps_name(self):
        pm = _make_map(high={"tier": "high"}, low={"tier": "low"})
        with pm.override("high", "low"):
            assert pm.get("high").options == {"tier": "low"}

    def test_override_does_not_affect_other_names(self):
        pm = _make_map(high={"tier": "high"}, low={"tier": "low"})
        with pm.override("high", "low"):
            assert pm.get("low").options == {"tier": "low"}

    def test_override_restores_on_exit(self):
        pm = _make_map(high={"tier": "high"}, low={"tier": "low"})
        with pm.override("high", "low"):
            assert pm.get("high").options == {"tier": "low"}
        assert pm.get("high").options == {"tier": "high"}

    def test_override_restores_on_exception(self):
        pm = _make_map(high={"tier": "high"}, low={"tier": "low"})
        with pytest.raises(ValueError):
            with pm.override("high", "low"):
                raise ValueError("boom")
        assert pm.get("high").options == {"tier": "high"}

    def test_nested_overrides(self):
        pm = _make_map(a={"v": "a"}, b={"v": "b"}, c={"v": "c"})
        with pm.override("a", "b"):
            assert pm.get("a").options == {"v": "b"}
            with pm.override("b", "c"):
                # inner override: b -> c
                assert pm.get("b").options == {"v": "c"}
                # transitive: a -> b -> c
                assert pm.get("a").options == {"v": "c"}
            # inner exited: b is back to normal
            assert pm.get("b").options == {"v": "b"}
        # everything back to normal
        assert pm.get("a").options == {"v": "a"}

    def test_chained_overrides_in_same_context(self):
        """Multiple overrides can be stacked via nesting."""
        pm = _make_map(a={"v": "a"}, b={"v": "b"}, c={"v": "c"})
        with pm.override("a", "b"):
            with pm.override("c", "b"):
                assert pm.get("a").options == {"v": "b"}
                assert pm.get("c").options == {"v": "b"}
                assert pm.get("b").options == {"v": "b"}

    def test_override_to_nonexistent_name_raises_on_get(self):
        pm = _make_map(a={})
        with pm.override("a", "nonexistent"):
            with pytest.raises(ValueError, match="'nonexistent' is not configured"):
                pm.get("a")

    def test_cycle_does_not_loop_forever(self):
        """If a -> b and b -> a, resolution stops without infinite loop."""
        pm = _make_map(a={"v": "a"}, b={"v": "b"})
        with pm.override("a", "b"):
            with pm.override("b", "a"):
                # a -> b -> a would cycle; stops at "a" (the last resolved)
                result = pm.get("a")
                assert result.options in ({"v": "a"}, {"v": "b"})

    def test_independent_provider_maps_have_independent_overrides(self):
        pm1 = _make_map(x={"v": "1a"}, y={"v": "1b"})
        pm2 = _make_map(x={"v": "2a"}, y={"v": "2b"})
        with pm1.override("x", "y"):
            assert pm1.get("x").options == {"v": "1b"}
            # pm2 is unaffected
            assert pm2.get("x").options == {"v": "2a"}
