# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Tests for type-safe LLM response validation in ask_llm_parallel.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from nlweb_core.llm import ask_llm_parallel
from nlweb_core.llm_models import RankingResponse, ScoreResponse, QuestionResponse
from nlweb_core.llm_exceptions import LLMValidationError


class TestAskLLMParallelValidation:
    """Tests for validation behavior in ask_llm_parallel."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config object with generative model providers."""
        config = MagicMock()
        # Set up mock generative model config
        mock_model_config = MagicMock()
        mock_model_config.options = {"model": "test-model"}
        config.get_generative_model_provider = MagicMock(return_value=mock_model_config)
        return config

    @pytest.fixture
    def mock_provider(self):
        """Create a mock LLM provider."""
        provider = MagicMock()
        provider.get_completions = AsyncMock()
        return provider

    @pytest.mark.asyncio
    async def test_validates_pydantic_model_results(self, mock_config, mock_provider):
        """Test that valid LLM responses are validated and converted to Pydantic models."""
        mock_provider.get_completions.return_value = [
            {"score": 85, "description": "Test item"},
            {"score": 70, "description": "Another item"},
        ]

        with patch("nlweb_core.llm.get_config", return_value=mock_config), \
             patch("nlweb_core.llm.get_generative_provider", return_value=mock_provider):

            results = await ask_llm_parallel(
                prompts=["prompt1", "prompt2"],
                schema=RankingResponse,
                level="low",
            )

            assert len(results) == 2
            assert isinstance(results[0], RankingResponse)
            assert results[0].score == 85
            assert results[0].description == "Test item"
            assert isinstance(results[1], RankingResponse)
            assert results[1].score == 70

    @pytest.mark.asyncio
    async def test_returns_validation_error_for_invalid_response(self, mock_config, mock_provider):
        """Test that invalid responses return LLMValidationError."""
        mock_provider.get_completions.return_value = [
            {"score": 85, "description": "Valid"},
            {"score": "not_a_number", "description": "Invalid"},  # Invalid score type
        ]

        with patch("nlweb_core.llm.get_config", return_value=mock_config), \
             patch("nlweb_core.llm.get_generative_provider", return_value=mock_provider):

            results = await ask_llm_parallel(
                prompts=["prompt1", "prompt2"],
                schema=RankingResponse,
                level="low",
            )

            assert len(results) == 2
            assert isinstance(results[0], RankingResponse)
            assert isinstance(results[1], LLMValidationError)
            assert results[1].raw_response == {"score": "not_a_number", "description": "Invalid"}

    @pytest.mark.asyncio
    async def test_returns_validation_error_for_missing_field(self, mock_config, mock_provider):
        """Test that responses missing required fields return LLMValidationError."""
        mock_provider.get_completions.return_value = [
            {"score": 85},  # Missing description
        ]

        with patch("nlweb_core.llm.get_config", return_value=mock_config), \
             patch("nlweb_core.llm.get_generative_provider", return_value=mock_provider):

            results = await ask_llm_parallel(
                prompts=["prompt1"],
                schema=RankingResponse,
                level="low",
            )

            assert len(results) == 1
            assert isinstance(results[0], LLMValidationError)
            assert "description" in str(results[0].validation_error) or "description" in str(results[0])

    @pytest.mark.asyncio
    async def test_passes_through_exceptions_unchanged(self, mock_config, mock_provider):
        """Test that exceptions from provider are passed through unchanged."""
        test_exception = ValueError("Provider error")
        mock_provider.get_completions.return_value = [
            {"score": 85, "description": "Valid"},
            test_exception,
        ]

        with patch("nlweb_core.llm.get_config", return_value=mock_config), \
             patch("nlweb_core.llm.get_generative_provider", return_value=mock_provider):

            results = await ask_llm_parallel(
                prompts=["prompt1", "prompt2"],
                schema=RankingResponse,
                level="low",
            )

            assert len(results) == 2
            assert isinstance(results[0], RankingResponse)
            assert results[1] is test_exception

    @pytest.mark.asyncio
    async def test_clamps_out_of_range_scores(self, mock_config, mock_provider):
        """Test that out-of-range scores are clamped by Pydantic validators."""
        mock_provider.get_completions.return_value = [
            {"score": 150, "description": "Over 100"},
            {"score": -20, "description": "Under 0"},
        ]

        with patch("nlweb_core.llm.get_config", return_value=mock_config), \
             patch("nlweb_core.llm.get_generative_provider", return_value=mock_provider):

            results = await ask_llm_parallel(
                prompts=["prompt1", "prompt2"],
                schema=RankingResponse,
                level="low",
            )

            assert len(results) == 2
            assert isinstance(results[0], RankingResponse)
            assert results[0].score == 100  # Clamped from 150
            assert isinstance(results[1], RankingResponse)
            assert results[1].score == 0  # Clamped from -20


class TestLLMValidationError:
    """Tests for LLMValidationError exception class."""

    def test_stores_raw_response(self):
        """Test that LLMValidationError stores the raw response."""
        raw = {"score": "invalid", "description": "test"}
        validation_err = ValueError("score must be int")
        error = LLMValidationError("Validation failed", raw, validation_err)

        assert error.raw_response == raw
        assert error.validation_error == validation_err
        assert "Validation failed" in str(error)

    def test_repr_includes_raw_response(self):
        """Test that repr includes raw response for debugging."""
        raw = {"score": "bad"}
        error = LLMValidationError("Failed", raw, ValueError("test"))

        repr_str = repr(error)
        assert "LLMValidationError" in repr_str
        assert "raw_response" in repr_str
