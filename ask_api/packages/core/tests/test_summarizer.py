"""
Tests for NLWeb summarizer module.
"""

import pytest
from unittest.mock import AsyncMock

from nlweb_core.summarizer import ResultsSummarizer, SummaryResult


class TestSummaryResult:
    """Tests for SummaryResult dataclass."""

    def test_summary_result_creation(self):
        """Test basic SummaryResult creation."""
        result = SummaryResult(
            summary="Test summary", raw_response={"summary": "Test summary"}
        )
        assert result.summary == "Test summary"
        assert result.raw_response == {"summary": "Test summary"}

    def test_to_result_object_returns_v054_format(self):
        """Test that to_result_object returns v0.54 protocol format."""
        result = SummaryResult(
            summary="Test summary", raw_response={"summary": "Test summary"}
        )
        obj = result.to_result_object()
        assert obj == {"@type": "Summary", "text": "Test summary"}


class TestResultsSummarizer:
    """Tests for ResultsSummarizer class."""

    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM callable."""
        mock = AsyncMock(return_value={"summary": "Mock summary of results"})
        return mock

    @pytest.fixture
    def sample_results(self):
        """Sample search results for testing."""
        return [
            {"name": "Result 1", "description": "Description of result 1"},
            {"name": "Result 2", "description": "Description of result 2"},
            {"name": "Result 3", "description": "Description of result 3"},
        ]

    def test_summarizer_initialization_with_defaults(self, mock_llm):
        """Test summarizer initializes with default values."""
        summarizer = ResultsSummarizer(llm=mock_llm)
        assert summarizer._llm == mock_llm
        assert summarizer._prompt_template == ResultsSummarizer.DEFAULT_PROMPT_TEMPLATE

    def test_summarizer_initialization_with_custom_prompt(self, mock_llm):
        """Test summarizer accepts custom prompt template."""
        custom_prompt = "Custom prompt: {query}\n{results}"
        summarizer = ResultsSummarizer(llm=mock_llm, prompt_template=custom_prompt)
        assert summarizer._prompt_template == custom_prompt

    def test_format_results_formats_all_provided_results(self, mock_llm, sample_results):
        """Test format_results formats all results provided by caller."""
        summarizer = ResultsSummarizer(llm=mock_llm)
        formatted = summarizer.format_results(sample_results)

        assert "1. Result 1: Description of result 1" in formatted
        assert "2. Result 2: Description of result 2" in formatted
        assert "3. Result 3: Description of result 3" in formatted

    def test_format_results_caller_controls_slice(self, mock_llm, sample_results):
        """Test that caller controls which results are formatted by slicing."""
        summarizer = ResultsSummarizer(llm=mock_llm)
        formatted = summarizer.format_results(sample_results[:2])

        assert "1. Result 1: Description of result 1" in formatted
        assert "2. Result 2: Description of result 2" in formatted
        assert "Result 3" not in formatted

    def test_format_results_handles_missing_fields(self, mock_llm):
        """Test format_results handles results with missing name/description."""
        results = [
            {"name": "Has name only"},
            {"description": "Has description only"},
            {},
        ]
        summarizer = ResultsSummarizer(llm=mock_llm)
        formatted = summarizer.format_results(results)

        assert "1. Has name only:" in formatted
        assert "2. Unknown: Has description only" in formatted
        assert "3. Unknown:" in formatted

    def test_format_results_empty_list(self, mock_llm):
        """Test format_results with empty results list."""
        summarizer = ResultsSummarizer(llm=mock_llm)
        formatted = summarizer.format_results([])
        assert formatted == ""

    def test_build_prompt_includes_query_and_results(self, mock_llm, sample_results):
        """Test build_prompt includes query and formatted results."""
        summarizer = ResultsSummarizer(llm=mock_llm)
        prompt = summarizer.build_prompt("test query", sample_results)

        assert "test query" in prompt
        assert "1. Result 1: Description of result 1" in prompt
        assert "2. Result 2: Description of result 2" in prompt
        assert "3. Result 3: Description of result 3" in prompt

    def test_build_prompt_uses_custom_template(self, mock_llm, sample_results):
        """Test build_prompt uses custom template when provided."""
        custom_template = "Query: {query}\nItems:\n{results}"
        summarizer = ResultsSummarizer(llm=mock_llm, prompt_template=custom_template)
        prompt = summarizer.build_prompt("my query", sample_results)

        assert prompt.startswith("Query: my query\nItems:\n")

    async def test_summarize_calls_llm_with_prompt_and_schema(
        self, mock_llm, sample_results
    ):
        """Test summarize calls LLM with prompt and schema only."""
        summarizer = ResultsSummarizer(llm=mock_llm)
        await summarizer.summarize("test query", sample_results)

        mock_llm.assert_called_once()
        call_args = mock_llm.call_args
        assert "test query" in call_args[0][0]  # prompt contains query
        assert call_args[0][1] == ResultsSummarizer.SCHEMA

    async def test_summarize_returns_summary_result(self, mock_llm, sample_results):
        """Test summarize returns SummaryResult on success."""
        mock_llm.return_value = {"summary": "LLM generated summary"}
        summarizer = ResultsSummarizer(llm=mock_llm)
        result = await summarizer.summarize("test query", sample_results)

        assert isinstance(result, SummaryResult)
        assert result.summary == "LLM generated summary"
        assert result.raw_response == {"summary": "LLM generated summary"}

    async def test_summarize_returns_none_for_empty_results(self, mock_llm):
        """Test summarize returns None when results list is empty."""
        summarizer = ResultsSummarizer(llm=mock_llm)
        result = await summarizer.summarize("test query", [])

        assert result is None
        mock_llm.assert_not_called()

    async def test_summarize_raises_when_llm_fails(self, mock_llm, sample_results):
        """Test summarize raises exception when LLM raises exception."""
        mock_llm.side_effect = Exception("LLM error")
        summarizer = ResultsSummarizer(llm=mock_llm)

        with pytest.raises(Exception, match="LLM error"):
            await summarizer.summarize("test query", sample_results)

    async def test_summarize_raises_when_response_missing_summary(
        self, mock_llm, sample_results
    ):
        """Test summarize raises ValueError when LLM response lacks summary key."""
        mock_llm.return_value = {"other_key": "value"}
        summarizer = ResultsSummarizer(llm=mock_llm)

        with pytest.raises(ValueError, match="LLM response missing 'summary' field"):
            await summarizer.summarize("test query", sample_results)

    async def test_summarize_raises_when_response_is_none(
        self, mock_llm, sample_results
    ):
        """Test summarize raises ValueError when LLM returns None."""
        mock_llm.return_value = None
        summarizer = ResultsSummarizer(llm=mock_llm)

        with pytest.raises(ValueError, match="LLM response missing 'summary' field"):
            await summarizer.summarize("test query", sample_results)
