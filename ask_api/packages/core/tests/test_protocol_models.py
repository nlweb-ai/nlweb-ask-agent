"""
Tests for NLWeb protocol models.
"""

import pytest
from nlweb_core.protocol import AskRequest, Query
from pydantic import ValidationError


def test_valid_minimal_request():
    """Test that a minimal valid request works."""
    request = AskRequest(
        query=Query(text="test query", decontextualized_query=None),
        context=None,
        prefer=None,
        meta=None,
    )

    assert request.query.text == "test query"


class TestQueryExplicitFields:
    """Tests for explicit Query fields."""

    def test_query_with_all_explicit_fields(self):
        """Test Query with all explicit optional fields."""
        query = Query(
            text="test query",
            site="example.com",
            num_results=100,
            max_results=20,
            min_score=70,
        )
        assert query.text == "test query"
        assert query.site == "example.com"
        assert query.num_results == 100
        assert query.max_results == 20
        assert query.min_score == 70

    def test_query_field_defaults(self):
        """Test that fields have expected defaults."""
        query = Query(text="test query")
        # Fields with actual defaults
        assert query.site == "all"
        assert query.num_results == 50
        assert query.max_results == 9
        assert query.min_score == 51
        # Fields that remain optional (None)
        assert query.decontextualized_query is None

    def test_effective_query_property(self):
        """Test effective_query property returns decontextualized_query or text."""
        # Without decontextualized_query
        query = Query(text="original query")
        assert query.effective_query == "original query"

        # With decontextualized_query
        query = Query(text="original", decontextualized_query="decontextualized")
        assert query.effective_query == "decontextualized"

    def test_query_extra_fields_rejected(self):
        """Test that unknown fields are rejected."""
        with pytest.raises(ValidationError):
            Query(
                text="test query",
                future_field="future_value",
            )

    def test_query_num_results_validation_lower_bound(self):
        """Test num_results rejects values below 1."""
        with pytest.raises(ValidationError):
            Query(text="test", num_results=0)

    def test_query_num_results_validation_upper_bound(self):
        """Test num_results rejects values above 1000."""
        with pytest.raises(ValidationError):
            Query(text="test", num_results=1001)

    def test_query_num_results_validation_valid_bounds(self):
        """Test num_results accepts valid boundary values."""
        query_min = Query(text="test", num_results=1)
        query_max = Query(text="test", num_results=1000)
        assert query_min.num_results == 1
        assert query_max.num_results == 1000

    def test_query_max_results_validation(self):
        """Test max_results field validation."""
        with pytest.raises(ValidationError):
            Query(text="test", max_results=0)
        with pytest.raises(ValidationError):
            Query(text="test", max_results=101)

        query = Query(text="test", max_results=50)
        assert query.max_results == 50

    def test_query_min_score_validation(self):
        """Test min_score field validation."""
        with pytest.raises(ValidationError):
            Query(text="test", min_score=-1)
        with pytest.raises(ValidationError):
            Query(text="test", min_score=101)

        query = Query(text="test", min_score=0)
        assert query.min_score == 0
        query = Query(text="test", min_score=100)
        assert query.min_score == 100
