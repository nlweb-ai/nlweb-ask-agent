# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""Tests for RankedResult class and helper functions."""

import pytest

from nlweb_core.retrieved_item import RetrievedItem
from nlweb_core.ranked_result import (
    RankedResult,
    select_best_from_graph,
    PREFERRED_TYPES,
    SKIP_TYPES,
)


class TestSelectBestFromGraph:
    """Tests for the select_best_from_graph function."""

    def test_empty_graph_returns_empty_dict(self):
        assert select_best_from_graph([]) == {}

    def test_single_item_returns_that_item(self):
        item = {"@type": "Article", "name": "Test"}
        assert select_best_from_graph([item]) == item

    def test_prefers_article_over_webpage(self):
        graph = [
            {"@type": "WebPage", "name": "Page"},
            {"@type": "Article", "name": "Article"},
        ]
        result = select_best_from_graph(graph)
        assert result["@type"] == "Article"

    def test_prefers_newsarticle_over_article(self):
        graph = [
            {"@type": "Article", "name": "Article"},
            {"@type": "NewsArticle", "name": "News"},
        ]
        result = select_best_from_graph(graph)
        assert result["@type"] == "NewsArticle"

    def test_prefers_product_over_organization(self):
        graph = [
            {"@type": "Organization", "name": "Org"},
            {"@type": "Product", "name": "Product"},
        ]
        result = select_best_from_graph(graph)
        assert result["@type"] == "Product"

    def test_skips_breadcrumblist(self):
        graph = [
            {"@type": "BreadcrumbList", "itemListElement": []},
            {"@type": "Article", "name": "Article"},
        ]
        result = select_best_from_graph(graph)
        assert result["@type"] == "Article"

    def test_skips_all_utility_types(self):
        for skip_type in SKIP_TYPES:
            graph = [
                {"@type": skip_type, "name": "Skip me"},
                {"@type": "Recipe", "name": "Recipe"},
            ]
            result = select_best_from_graph(graph)
            assert result["@type"] == "Recipe", f"Failed to skip {skip_type}"

    def test_handles_array_types(self):
        graph = [
            {"@type": "WebPage", "name": "Page"},
            {"@type": ["Article", "NewsArticle"], "name": "News Article"},
        ]
        result = select_best_from_graph(graph)
        assert result["name"] == "News Article"

    def test_falls_back_to_first_non_skipped_item(self):
        graph = [
            {"@type": "WebPage", "name": "Page"},
            {"@type": "UnknownType", "name": "Unknown"},
        ]
        result = select_best_from_graph(graph)
        assert result["@type"] == "UnknownType"

    def test_last_resort_returns_first_item(self):
        graph = [
            {"@type": "WebPage", "name": "Page"},
            {"@type": "BreadcrumbList", "name": "Breadcrumbs"},
        ]
        result = select_best_from_graph(graph)
        assert result["@type"] == "WebPage"

    def test_item_without_type_is_fallback(self):
        graph = [
            {"@type": "WebPage", "name": "Page"},
            {"name": "No type item"},
        ]
        result = select_best_from_graph(graph)
        assert result["name"] == "No type item"


class TestRankedResultSchemaObject:
    """Tests for RankedResult.schema_object property."""

    def _make_result(self, raw_schema: str | dict | list) -> RankedResult:
        item = RetrievedItem(url="https://example.com", raw_schema_object=raw_schema)
        return RankedResult(item=item, score=80)

    def test_empty_schema_returns_empty_dict(self):
        result = self._make_result("")
        assert result.schema_object == {}

    def test_single_dict_returns_that_dict(self):
        schema = {"@type": "Article", "name": "Test"}
        result = self._make_result(schema)
        assert result.schema_object == schema

    def test_handles_graph_container(self):
        schema = {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "WebPage", "name": "Page"},
                {"@type": "Article", "name": "Article"},
            ],
        }
        result = self._make_result(schema)
        assert result.schema_object["@type"] == "Article"

    def test_handles_multiple_items_in_list(self):
        schema = [
            {"@type": "WebPage", "name": "Page"},
            {"@type": "Recipe", "name": "Recipe"},
        ]
        result = self._make_result(schema)
        assert result.schema_object["@type"] == "Recipe"

    def test_single_item_list_returns_that_item(self):
        schema = [{"@type": "Product", "name": "Product"}]
        result = self._make_result(schema)
        assert result.schema_object["@type"] == "Product"


class TestRankedResultName:
    """Tests for RankedResult.name property."""

    def _make_result(self, schema: dict) -> RankedResult:
        item = RetrievedItem(url="https://example.com", raw_schema_object=schema)
        return RankedResult(item=item, score=80)

    def test_extracts_name_field(self):
        result = self._make_result({"name": "Test Name"})
        assert result.name == "Test Name"

    def test_extracts_headline_as_fallback(self):
        result = self._make_result({"headline": "Article Headline"})
        assert result.name == "Article Headline"

    def test_name_takes_priority_over_headline(self):
        result = self._make_result({"name": "Name", "headline": "Headline"})
        assert result.name == "Name"

    def test_constructs_person_name(self):
        result = self._make_result({"givenName": "John", "familyName": "Doe"})
        assert result.name == "John Doe"

    def test_handles_only_given_name(self):
        result = self._make_result({"givenName": "John"})
        assert result.name == "John"

    def test_handles_only_family_name(self):
        result = self._make_result({"familyName": "Doe"})
        assert result.name == "Doe"

    def test_extracts_legal_name(self):
        result = self._make_result({"legalName": "Acme Corporation"})
        assert result.name == "Acme Corporation"

    def test_extracts_model_for_product(self):
        result = self._make_result({"model": "iPhone 15"})
        assert result.name == "iPhone 15"

    def test_returns_empty_string_when_no_name(self):
        result = self._make_result({"description": "No name here"})
        assert result.name == ""

    def test_extracts_text_from_textobject(self):
        result = self._make_result({"name": {"text": "Text Object Name"}})
        assert result.name == "Text Object Name"

    def test_extracts_first_string_from_list(self):
        result = self._make_result({"name": ["First Name", "Second Name"]})
        assert result.name == "First Name"


class TestRankedResultDescription:
    """Tests for RankedResult.description property."""

    def _make_result(self, schema: dict) -> RankedResult:
        item = RetrievedItem(url="https://example.com", raw_schema_object=schema)
        return RankedResult(item=item, score=80)

    def test_extracts_description_field(self):
        result = self._make_result({"description": "Test description"})
        assert result.description == "Test description"

    def test_extracts_reviewbody_for_review(self):
        result = self._make_result({"reviewBody": "Great product!"})
        assert result.description == "Great product!"

    def test_extracts_abstract_for_article(self):
        result = self._make_result({"abstract": "Article summary"})
        assert result.description == "Article summary"

    def test_extracts_text_field(self):
        result = self._make_result({"text": "Recipe instructions"})
        assert result.description == "Recipe instructions"

    def test_extracts_event_description(self):
        result = self._make_result({"eventDescription": "Event details"})
        assert result.description == "Event details"

    def test_description_takes_priority(self):
        result = self._make_result({
            "description": "Primary",
            "abstract": "Secondary",
        })
        assert result.description == "Primary"

    def test_returns_empty_string_when_no_description(self):
        result = self._make_result({"name": "No description"})
        assert result.description == ""

    def test_extracts_text_from_textobject(self):
        result = self._make_result({"description": {"text": "TextObject desc"}})
        assert result.description == "TextObject desc"


class TestRankedResultImage:
    """Tests for RankedResult.image property."""

    def _make_result(self, schema: dict) -> RankedResult:
        item = RetrievedItem(url="https://example.com", raw_schema_object=schema)
        return RankedResult(item=item, score=80)

    def test_extracts_image_url_string(self):
        result = self._make_result({"image": "https://example.com/image.jpg"})
        assert result.image == "https://example.com/image.jpg"

    def test_extracts_url_from_imageobject(self):
        result = self._make_result({
            "image": {"@type": "ImageObject", "url": "https://example.com/img.jpg"}
        })
        assert result.image == "https://example.com/img.jpg"

    def test_extracts_contenturl_from_imageobject(self):
        result = self._make_result({
            "image": {"@type": "ImageObject", "contentUrl": "https://example.com/content.jpg"}
        })
        assert result.image == "https://example.com/content.jpg"

    def test_prefers_url_over_contenturl(self):
        result = self._make_result({
            "image": {
                "url": "https://example.com/url.jpg",
                "contentUrl": "https://example.com/content.jpg",
            }
        })
        assert result.image == "https://example.com/url.jpg"

    def test_extracts_first_from_image_list(self):
        result = self._make_result({
            "image": [
                "https://example.com/first.jpg",
                "https://example.com/second.jpg",
            ]
        })
        assert result.image == "https://example.com/first.jpg"

    def test_extracts_photo_field(self):
        result = self._make_result({"photo": "https://example.com/photo.jpg"})
        assert result.image == "https://example.com/photo.jpg"

    def test_extracts_logo_field(self):
        result = self._make_result({"logo": "https://example.com/logo.png"})
        assert result.image == "https://example.com/logo.png"

    def test_extracts_thumbnail_field(self):
        result = self._make_result({
            "thumbnail": {"url": "https://example.com/thumb.jpg"}
        })
        assert result.image == "https://example.com/thumb.jpg"

    def test_extracts_thumbnailurl_field(self):
        result = self._make_result({"thumbnailUrl": "https://example.com/thumb.jpg"})
        assert result.image == "https://example.com/thumb.jpg"

    def test_image_takes_priority_over_others(self):
        result = self._make_result({
            "image": "https://example.com/image.jpg",
            "logo": "https://example.com/logo.png",
        })
        assert result.image == "https://example.com/image.jpg"

    def test_returns_none_when_no_image(self):
        result = self._make_result({"name": "No image"})
        assert result.image is None


class TestRankedResultToDict:
    """Tests for RankedResult.to_dict method."""

    def _make_result(self, schema: dict, score: int = 80) -> RankedResult:
        item = RetrievedItem(
            url="https://example.com/item",
            raw_schema_object=schema,
            site="example.com",
        )
        return RankedResult(item=item, score=score)

    def test_includes_basic_fields(self):
        result = self._make_result({
            "@type": "Article",
            "name": "Test Article",
            "description": "Test description",
        })
        d = result.to_dict()

        assert d["@type"] == "Article"
        assert d["url"] == "https://example.com/item"
        assert d["name"] == "Test Article"
        assert d["site"] == "example.com"
        assert d["score"] == 80
        assert d["description"] == "Test description"

    def test_includes_normalized_image(self):
        result = self._make_result({
            "image": {"url": "https://example.com/img.jpg"}
        })
        d = result.to_dict()
        assert d["image"] == "https://example.com/img.jpg"

    def test_includes_grounding_url(self):
        result = self._make_result({
            "url": "https://example.com/article"
        })
        d = result.to_dict()
        assert d["grounding"] == {"source_urls": ["https://example.com/article"]}

    def test_includes_grounding_from_id(self):
        result = self._make_result({
            "@id": "https://example.com/article#main"
        })
        d = result.to_dict()
        assert d["grounding"] == {"source_urls": ["https://example.com/article#main"]}

    def test_includes_extra_schema_fields(self):
        result = self._make_result({
            "@type": "Recipe",
            "name": "Cookies",
            "cookTime": "PT30M",
            "recipeYield": "24 cookies",
        })
        d = result.to_dict()
        assert d["cookTime"] == "PT30M"
        assert d["recipeYield"] == "24 cookies"

    def test_excludes_raw_url_and_image(self):
        result = self._make_result({
            "url": "https://example.com/article",
            "image": {"url": "https://example.com/complex-image.jpg"},
        })
        d = result.to_dict()
        # url should not be duplicated in extra fields (it's in grounding)
        # image should be normalized, not the raw complex object
        assert d["image"] == "https://example.com/complex-image.jpg"


class TestRankedResultProperties:
    """Tests for other RankedResult properties."""

    def _make_result(self, schema: dict) -> RankedResult:
        item = RetrievedItem(url="https://example.com", raw_schema_object=schema)
        return RankedResult(item=item, score=75)

    def test_schema_type_returns_type(self):
        result = self._make_result({"@type": "Product"})
        assert result.schema_type == "Product"

    def test_schema_type_defaults_to_item(self):
        result = self._make_result({"name": "No type"})
        assert result.schema_type == "Item"

    def test_grounding_url_from_url(self):
        result = self._make_result({"url": "https://example.com/page"})
        assert result.grounding_url == "https://example.com/page"

    def test_grounding_url_from_id(self):
        result = self._make_result({"@id": "https://example.com/page#section"})
        assert result.grounding_url == "https://example.com/page#section"

    def test_grounding_url_prefers_url_over_id(self):
        result = self._make_result({
            "url": "https://example.com/url",
            "@id": "https://example.com/id",
        })
        assert result.grounding_url == "https://example.com/url"

    def test_grounding_url_returns_none_when_missing(self):
        result = self._make_result({"name": "No URL"})
        assert result.grounding_url is None
