# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
RankedResult class for representing scored search results with schema.org data extraction.

This module provides intelligent extraction of name, description, and image from
various schema.org types, handling @graph containers and selecting the most
relevant content item.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nlweb_core.retrieved_item import RetrievedItem

# Content types ranked by preference (most specific/valuable first)
PREFERRED_TYPES: tuple[str, ...] = (
    # Articles & News
    "NewsArticle",
    "Article",
    "BlogPosting",
    "ScholarlyArticle",
    "TechArticle",
    "Report",
    # Commerce
    "Product",
    "Offer",
    # Food & Recipes
    "Recipe",
    "Menu",
    "MenuItem",
    # Events & Places
    "Event",
    "Place",
    "LocalBusiness",
    "Restaurant",
    # Media
    "VideoObject",
    "AudioObject",
    "ImageObject",
    "Movie",
    "TVSeries",
    "MusicRecording",
    "Book",
    # How-to & FAQ
    "HowTo",
    "FAQPage",
    "QAPage",
    # People & Organizations
    "Person",
    "Organization",
    # Generic creative work (lower priority)
    "CreativeWork",
    # Review at the bottom, so the thing being reviewed is preferred
    "Review",
)

# Types to skip (utility/structural types)
SKIP_TYPES: frozenset[str] = frozenset(
    {
        "WebPage",
        "WebSite",
        "BreadcrumbList",
        "ItemList",
        "SearchAction",
        "ReadAction",
        "SiteNavigationElement",
        "WPHeader",
        "WPFooter",
        "WPSideBar",
    }
)


def select_best_from_graph(graph: list[dict[str, Any]]) -> dict[str, Any]:
    """Select the best/most relevant item from a @graph array or list of schema objects.

    Args:
        graph: List of schema.org objects to select from.

    Returns:
        The most relevant schema object based on type priority, or empty dict if none.
    """
    if not graph:
        return {}

    # Build a map of type -> items
    by_type: dict[str, list[dict[str, Any]]] = {}

    for item in graph:
        item_type = item.get("@type", "")
        # Handle array types like ["Article", "NewsArticle"]
        if isinstance(item_type, list):
            types = item_type
        else:
            types = [item_type] if item_type else []

        # Skip utility types
        if any(t in SKIP_TYPES for t in types):
            continue

        # Group by type
        for t in types:
            by_type.setdefault(t, []).append(item)

    # Find first match in preferred order
    for preferred in PREFERRED_TYPES:
        if preferred in by_type:
            return by_type[preferred][0]

    # Return first non-skipped item, or first item overall
    for item in graph:
        item_type = item.get("@type", "")
        types = item_type if isinstance(item_type, list) else [item_type]
        if not any(t in SKIP_TYPES for t in types):
            return item

    # Last resort: return first item
    return graph[0] if graph else {}


@dataclass
class RankedResult:
    """A ranked search result with score and normalized schema data.

    Provides intelligent extraction of name, description, and image from
    various schema.org types. Handles @graph containers and multi-item
    schema objects by selecting the most relevant content type.
    """

    item: RetrievedItem
    score: int
    sent: bool = False

    @property
    def schema_object(self) -> dict[str, Any]:
        """Get the primary schema object, selecting best from list or @graph."""
        if not self.item.schema_object:
            return {}

        items = self.item.schema_object

        # If multiple items, select the best one
        if len(items) > 1:
            return select_best_from_graph(items)

        first = items[0]

        # Check if this is a @graph container
        if "@graph" in first and isinstance(first["@graph"], list):
            return select_best_from_graph(first["@graph"])

        return first

    @property
    def schema_type(self) -> str:
        """Get the @type of the schema object."""
        return self.schema_object.get("@type", "Item")

    def _extract_text(self, value: Any) -> str | None:
        """Extract text from a schema.org value that may be string, TextObject, or list."""
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, list) and value:
            # Take first string element from list
            for item in value:
                if isinstance(item, str):
                    return item
                if isinstance(item, dict) and "text" in item:
                    return str(item["text"])
            return None
        if isinstance(value, dict):
            # TextObject or similar - extract text property
            if "text" in value:
                return str(value["text"])
            if "name" in value:
                return str(value["name"])
        return None

    @property
    def name(self) -> str:
        """Extract name from schema object, checking common schema.org name fields."""
        obj = self.schema_object

        # Primary: explicit name field
        if name := self._extract_text(obj.get("name")):
            return name

        # Articles/CreativeWork: headline
        if headline := self._extract_text(obj.get("headline")):
            return headline

        # Person: construct from given/family name
        given = self._extract_text(obj.get("givenName")) or ""
        family = self._extract_text(obj.get("familyName")) or ""
        if given or family:
            return f"{given} {family}".strip()

        # Organization: legal name
        if legal_name := self._extract_text(obj.get("legalName")):
            return legal_name

        # Product: model or sku as fallback
        if model := self._extract_text(obj.get("model")):
            return model

        return ""

    @property
    def description(self) -> str:
        """Extract description from schema object, checking common schema.org fields."""
        obj = self.schema_object

        # Primary: explicit description field
        if desc := self._extract_text(obj.get("description")):
            return desc

        # Review: reviewBody
        if review_body := self._extract_text(obj.get("reviewBody")):
            return review_body

        # Article: abstract (preferred over full articleBody)
        if abstract := self._extract_text(obj.get("abstract")):
            return abstract

        # HowTo/Recipe: text field often contains description
        if text := self._extract_text(obj.get("text")):
            return text

        # Event: use eventDescription if available
        if event_desc := self._extract_text(obj.get("eventDescription")):
            return event_desc

        return ""

    def _extract_image_url(self, value: Any) -> str | None:
        """Extract image URL from a value that may be string, ImageObject, or list."""
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, list) and value:
            # Take first valid image from list
            for item in value:
                if url := self._extract_image_url(item):
                    return url
            return None
        if isinstance(value, dict):
            # ImageObject or MediaObject - check url, contentUrl, or nested image
            if url := value.get("url"):
                if isinstance(url, str):
                    return url
            if content_url := value.get("contentUrl"):
                if isinstance(content_url, str):
                    return content_url
        return None

    @property
    def image(self) -> str | None:
        """Extract image URL from schema object, checking common schema.org fields."""
        obj = self.schema_object

        # Primary: explicit image field
        if url := self._extract_image_url(obj.get("image")):
            return url

        # Person/Place: photo
        if url := self._extract_image_url(obj.get("photo")):
            return url

        # Organization/Brand/Product: logo
        if url := self._extract_image_url(obj.get("logo")):
            return url

        # VideoObject/CreativeWork: thumbnail or thumbnailUrl
        if url := self._extract_image_url(obj.get("thumbnail")):
            return url
        if thumbnail_url := obj.get("thumbnailUrl"):
            if isinstance(thumbnail_url, str):
                return thumbnail_url

        # WebPage: primaryImageOfPage
        if url := self._extract_image_url(obj.get("primaryImageOfPage")):
            return url

        # Recipe: specific image fields
        if url := self._extract_image_url(obj.get("recipeImage")):
            return url

        return None

    @property
    def grounding_url(self) -> str | None:
        """Get the URL for grounding/citation purposes."""
        return self.schema_object.get("url") or self.schema_object.get("@id")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict format for protocol output."""
        result: dict[str, Any] = {
            "@type": self.schema_type,
            "url": self.item.url,
            "name": self.name,
            "site": self.item.site,
            "score": self.score,
            "description": self.description,
        }

        # Add all schema attributes except url and image (handled specially)
        for key, value in self.schema_object.items():
            if key not in ("url", "image"):
                result[key] = value

        # Add normalized image if present
        if self.image:
            result["image"] = self.image

        # Add grounding if URL available
        if self.grounding_url:
            result["grounding"] = {"source_urls": [self.grounding_url]}

        return result
