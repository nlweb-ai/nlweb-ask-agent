# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Data types for retrieved items.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievedItem:
    """A single item retrieved from a search/retrieval operation."""

    url: str
    """The URL or identifier of the item."""

    raw_schema_object: str | dict[str, Any] | list[dict[str, Any]] = ""
    """The raw schema.org JSON data (string, dict, or list). Use schema_object property to access parsed value."""

    site: str = ""
    """The site this item belongs to."""

    _parsed_schema_object: list[dict[str, Any]] | None = field(
        default=None, repr=False, compare=False
    )
    """Cached parsed schema object. Use schema_object property to access."""

    @property
    def schema_object(self) -> list[dict[str, Any]]:
        """
        Parse and return the schema object as list[dict[str, Any]].

        Lazily parses raw_schema_object on first access and caches the result.

        Returns:
            Parsed schema object as list of dicts.

        Raises:
            ValueError: If raw_schema_object cannot be parsed as valid JSON or has invalid structure.
        """
        if self._parsed_schema_object is not None:
            return self._parsed_schema_object

        raw = self.raw_schema_object

        # If already a list, validate contents
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    raise ValueError(
                        f"schema_object list must contain dicts, got {type(item).__name__}"
                    )
            object.__setattr__(self, "_parsed_schema_object", raw)
            return raw

        # If string, parse as JSON
        if isinstance(raw, str):
            if not raw:
                # Empty string -> empty list
                object.__setattr__(self, "_parsed_schema_object", [])
                return []
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as e:
                raise ValueError(f"schema_object is not valid JSON: {e}")
            raw = parsed

        # If dict, wrap in list
        if isinstance(raw, dict):
            result = [raw]
            object.__setattr__(self, "_parsed_schema_object", result)
            return result

        # If list after parsing, validate and assign
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    raise ValueError(
                        f"schema_object list must contain dicts, got {type(item).__name__}"
                    )
            object.__setattr__(self, "_parsed_schema_object", raw)
            return raw

        # Invalid type
        raise ValueError(
            f"schema_object must be str, dict, or list[dict], got {type(raw).__name__}"
        )


