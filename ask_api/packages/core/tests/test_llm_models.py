# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Tests for LLM response Pydantic models.
"""

import pytest
from nlweb_core.llm_models import QuestionResponse, RankingResponse, ScoreResponse
from pydantic import ValidationError


class TestRankingResponse:
    """Tests for RankingResponse model."""

    def test_valid_response(self):
        """Test creating a valid RankingResponse."""
        response = RankingResponse(score=75, description="Highly relevant item")
        assert response.score == 75
        assert response.description == "Highly relevant item"

    def test_score_clamped_above_100(self):
        """Test that scores above 100 are clamped to 100."""
        response = RankingResponse(score=150, description="Test")
        assert response.score == 100

    def test_score_clamped_below_0(self):
        """Test that scores below 0 are clamped to 0."""
        response = RankingResponse(score=-10, description="Test")
        assert response.score == 0

    def test_score_boundary_0(self):
        """Test score at lower boundary."""
        response = RankingResponse(score=0, description="Test")
        assert response.score == 0

    def test_score_boundary_100(self):
        """Test score at upper boundary."""
        response = RankingResponse(score=100, description="Test")
        assert response.score == 100

    def test_float_score_converted_to_int(self):
        """Test that float scores are converted to int."""
        response = RankingResponse(score=75.9, description="Test")
        assert response.score == 75
        assert isinstance(response.score, int)

    def test_missing_score_raises_error(self):
        """Test that missing score raises ValidationError."""
        with pytest.raises(ValidationError):
            RankingResponse(description="Test")

    def test_missing_description_raises_error(self):
        """Test that missing description raises ValidationError."""
        with pytest.raises(ValidationError):
            RankingResponse(score=75)

    def test_model_validate_from_dict(self):
        """Test creating model from dict using model_validate."""
        data = {"score": 80, "description": "Good match"}
        response = RankingResponse.model_validate(data)
        assert response.score == 80
        assert response.description == "Good match"


class TestScoreResponse:
    """Tests for ScoreResponse model."""

    def test_valid_response(self):
        """Test creating a valid ScoreResponse."""
        response = ScoreResponse(score=85)
        assert response.score == 85

    def test_score_clamped_above_100(self):
        """Test that scores above 100 are clamped to 100."""
        response = ScoreResponse(score=200)
        assert response.score == 100

    def test_score_clamped_below_0(self):
        """Test that scores below 0 are clamped to 0."""
        response = ScoreResponse(score=-50)
        assert response.score == 0

    def test_float_score_converted_to_int(self):
        """Test that float scores are converted to int."""
        response = ScoreResponse(score=42.7)
        assert response.score == 42
        assert isinstance(response.score, int)

    def test_missing_score_raises_error(self):
        """Test that missing score raises ValidationError."""
        with pytest.raises(ValidationError):
            ScoreResponse()

    def test_model_validate_from_dict(self):
        """Test creating model from dict using model_validate."""
        data = {"score": 70}
        response = ScoreResponse.model_validate(data)
        assert response.score == 70


class TestQuestionResponse:
    """Tests for QuestionResponse model."""

    def test_valid_response(self):
        """Test creating a valid QuestionResponse."""
        response = QuestionResponse(question="What is your location?")
        assert response.question == "What is your location?"

    def test_empty_question_raises_error(self):
        """Test that empty question raises ValidationError."""
        with pytest.raises(ValidationError):
            QuestionResponse(question="")

    def test_missing_question_raises_error(self):
        """Test that missing question raises ValidationError."""
        with pytest.raises(ValidationError):
            QuestionResponse()

    def test_model_validate_from_dict(self):
        """Test creating model from dict using model_validate."""
        data = {"question": "Where are you located?"}
        response = QuestionResponse.model_validate(data)
        assert response.question == "Where are you located?"
