# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Common utility functions used across NLWeb.
"""

import json
import logging
from typing import Any, Dict, List, Union

# DEBUG: Temporary logging for trim_json testing - REMOVE BEFORE PRODUCTION
logger = logging.getLogger(__name__)


def get_param(
    query_params: Dict[str, Any],
    param_name: str,
    param_type: type = str,
    default_value: Any = None,
) -> Any:
    """
    Get a parameter from query_params with type conversion.

    Args:
        query_params: Dictionary of query parameters
        param_name: Name of the parameter to retrieve
        param_type: Type to convert the parameter to (str, int, float, bool, list)
        default_value: Default value if parameter not found

    Returns:
        The parameter value converted to the specified type, or default_value
    """
    value = query_params.get(param_name, default_value)
    if value is not None:
        if param_type == str:
            if isinstance(value, list):
                return value[0] if value else ""
            return value
        elif param_type == int:
            return int(value)
        elif param_type == float:
            return float(value)
        elif param_type == bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, list):
                return value[0].lower() == "true"
            return value.lower() == "true"
        elif param_type == list:
            if isinstance(value, list):
                return value
            return [
                item.strip() for item in value.strip("[]").split(",") if item.strip()
            ]
        else:
            raise ValueError(f"Unsupported parameter type: {param_type}")
    return default_value


def jsonify(obj):
    """Convert a string to JSON object if it's a JSON string, otherwise return as-is."""
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except json.JSONDecodeError:
            return obj
    return obj


# Schema.org types that should be skipped entirely
SKIP_TYPES = {
    "ListItem",
    "ItemList",
    "Organization",
    "BreadcrumbList",
    "Breadcrumb",
    "WebSite",
    "SearchAction",
    "SiteNavigationElement",
    "WebPageElement",
    "WebPage",
    "NewsMediaOrganization",
    "MerchantReturnPolicy",
    "ReturnPolicy",
    "CollectionPage",
    "Brand",
    "Corporation",
    "ReadAction",
}

# Properties to remove from all schema.org objects
SKIP_PROPERTIES = {
    "publisher",
    "mainEntityOfPage",
    "potentialAction",
    "image",
    "thumbnailUrl",
    "url",  # Remove URL fields - no semantic value for ranking
    "contentUrl",
    "embedUrl",
    "sameAs",  # Other common URL properties
    "width",
    "height",  # Layout properties - irrelevant for ranking
}


def _should_skip_item(item):
    """Determine if a schema.org item should be skipped based on its type."""
    if item is None:
        return True
    if "@type" not in item:
        return False

    item_type = item["@type"]
    # Handle both string and list @type values
    if isinstance(item_type, str):
        return item_type in SKIP_TYPES
    elif isinstance(item_type, list):
        return any(t in SKIP_TYPES for t in item_type)
    return False


def _trim_json_item(obj):
    """
    Trim a single schema.org item, removing unnecessary fields and simplifying complex ones.

    Applies smart field handling:
    - Images: Extracts URL from ImageObject or picks first from list
    - Person objects: Simplifies to just the name
    - Ratings: Extracts just the ratingValue
    - Reviews: Keeps up to 3 longest review bodies
    - Skips unnecessary metadata fields
    """
    if obj is None or not isinstance(obj, dict):
        return obj

    if _should_skip_item(obj):
        return None

    trimmed = {}

    for key, value in obj.items():
        # Skip configured properties
        if key in SKIP_PROPERTIES:
            continue

        # Image handling: extract URL from ImageObject or pick first from list
        if key == "image":
            if isinstance(value, list) and len(value) > 0:
                if all(isinstance(img, str) for img in value):
                    trimmed[key] = value[0]
                    continue
            elif (
                isinstance(value, dict)
                and value.get("@type") == "ImageObject"
                and "url" in value
            ):
                trimmed[key] = value["url"]
                continue

        # Person handling: simplify to just name
        if (
            isinstance(value, dict)
            and value.get("@type") == "Person"
            and "name" in value
        ):
            trimmed[key] = value["name"]
            continue

        # Rating handling: extract just the value
        if (
            key == "aggregateRating"
            and isinstance(value, dict)
            and "ratingValue" in value
        ):
            trimmed[key] = value["ratingValue"]
            continue

        # Review handling: keep up to 3 longest review bodies
        if key == "review" and isinstance(value, list):
            review_bodies = [
                (r.get("reviewBody", ""), r)
                for r in value
                if isinstance(r, dict) and "reviewBody" in r
            ]
            if review_bodies:
                # Sort by length descending, take top 3
                review_bodies.sort(key=lambda x: len(x[0]), reverse=True)
                trimmed[key] = [review for _, review in review_bodies[:3]]
                continue

        # Type-specific trimming for backward compatibility
        if "@type" in obj:
            obj_type = (
                obj["@type"] if isinstance(obj["@type"], list) else [obj["@type"]]
            )

            # Recipe-specific: skip certain fields
            # Note: Keeping datePublished for freshness-aware ranking
            if "Recipe" in obj_type and key in {
                "dateModified",
                "author",
            }:
                continue

            # Movie/TVSeries-specific: skip certain fields
            # Note: Keeping datePublished for freshness-aware ranking
            if ("Movie" in obj_type or "TVSeries" in obj_type) and key in {
                "dateModified",
                "author",
                "trailer",
            }:
                continue

        # Keep everything else
        trimmed[key] = value

    return trimmed if trimmed else None


def _trim_json_graph(graph_items):
    """Trim a @graph structure, filtering out unwanted types."""
    if not isinstance(graph_items, list):
        return None

    # Process all non-skipped items
    trimmed_items = []
    for item in graph_items:
        trimmed = trim_json(item)
        if trimmed is not None:
            trimmed_items.append(trimmed)

    return trimmed_items if trimmed_items else None


def trim_json(obj):
    """
    Trim schema.org JSON object, removing unnecessary fields and simplifying complex ones.

    Handles:
    - @graph structures
    - Lists of objects
    - Single objects
    - Smart field simplification (images, persons, ratings, reviews)
    - Type-based filtering

    Args:
        obj: JSON object (dict), list, or JSON string to trim

    Returns:
        Trimmed JSON object, list, or None if should be skipped
    """
    # DEBUG: Print input JSON - REMOVE BEFORE PRODUCTION
    # print(f"\n{'='*80}\n[TRIM_JSON_INPUT] Original JSON:\n{json.dumps(obj, indent=2) if isinstance(obj, (dict, list)) else obj}\n{'='*80}")

    obj = jsonify(obj)

    # Handle @graph structures
    if isinstance(obj, dict) and "@graph" in obj:
        trimmed = _trim_json_graph(obj["@graph"])
        # DEBUG: Print output after @graph processing - REMOVE BEFORE PRODUCTION
        # print(f"\n{'='*80}\n[TRIM_JSON_OUTPUT] Trimmed @graph result:\n{json.dumps(trimmed, indent=2) if trimmed else None}\n{'='*80}")
        return trimmed if trimmed else None

    # Handle lists
    if isinstance(obj, list):
        trimmed_items = []
        for item in obj:
            trimmed = trim_json(item)
            if trimmed is not None:
                trimmed_items.append(trimmed)
        # DEBUG: Print output after list processing - REMOVE BEFORE PRODUCTION
        # print(f"\n{'='*80}\n[TRIM_JSON_OUTPUT] Trimmed list result:\n{json.dumps(trimmed_items, indent=2) if trimmed_items else None}\n{'='*80}")
        return trimmed_items if trimmed_items else None

    # Handle single objects
    if isinstance(obj, dict):
        trimmed = _trim_json_item(obj)
        # DEBUG: Print output after single object processing - REMOVE BEFORE PRODUCTION
        # print(f"\n{'='*80}\n[TRIM_JSON_OUTPUT] Trimmed object result:\n{json.dumps(trimmed, indent=2) if trimmed else None}\n{'='*80}")
        return trimmed

    # DEBUG: Print passthrough - REMOVE BEFORE PRODUCTION
    # print(f"\n{'='*80}\n[TRIM_JSON_OUTPUT] Passthrough (no trimming): {obj}\n{'='*80}")
    return obj


def fill_prompt_variables(prompt_str, *param_dicts):
    """
    Substitute variables in the prompt string with values from one or more param dicts.

    Variables in the prompt are in the format {variable.attribute} or {variable}.
    For example: {request.site}, {site.itemType}, {item.description}

    Args:
        prompt_str: The prompt string with variables to substitute
        *param_dicts: One or more dicts of parameters to substitute. Later dicts override earlier ones.
                      (e.g., {'request.site': 'example.com'}, {'item.description': 'text'})

    Returns:
        The prompt string with variables substituted
    """
    if not param_dicts:
        return prompt_str

    # Iterate through all provided dicts
    for params in param_dicts:
        if params:
            for key, value in params.items():
                placeholder = "{" + key + "}"
                # Ensure value is a string
                if not isinstance(value, str):
                    value = str(value)
                prompt_str = prompt_str.replace(placeholder, value)

    return prompt_str
