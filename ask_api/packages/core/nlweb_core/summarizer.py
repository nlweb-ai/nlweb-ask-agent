# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Standalone summarizer with injectable LLM for evaluation and testing.

This module provides a ResultsSummarizer class that can be used independently
of the handler for summarizing search results. It supports injectable LLM
callables for flexibility in testing and evaluation scenarios.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

from dataclasses import dataclass
from functools import partial
from typing import Any, Awaitable, Callable, Dict, List, Optional


@dataclass
class SummaryResult:
    """Result of a summarization operation."""

    summary: str
    raw_response: Dict[str, Any]

    def to_result_object(self) -> Dict[str, Any]:
        """Convert to v0.54 protocol format."""
        return {"@type": "Summary", "text": self.summary}


class ResultsSummarizer:
    """Standalone summarizer with injectable LLM.

    This class extracts summarization logic from PostQueryProcessing to allow:
    1. Independent usage in evaluation harnesses
    2. Testing with mock LLMs
    3. Custom prompt configurations

    Example usage with custom LLM:
        async def my_test_llm(prompt, schema):
            return {"summary": "Test summary"}

        summarizer = ResultsSummarizer(llm=my_test_llm)
        result = await summarizer.summarize(query="test", results=[...])

    Example with partial for production:
        from functools import partial
        from nlweb_core.llm import ask_llm

        llm = partial(ask_llm, level='high', timeout=20)
        summarizer = ResultsSummarizer(llm=llm)
    """

    DEFAULT_PROMPT_TEMPLATE = """Summarize the following search results in 2-3 sentences, highlighting the key information that answers the user's question: {query}

Results:
{results}"""

    SCHEMA = {"summary": "A 2-3 sentence summary of the results"}

    def __init__(
        self,
        llm: Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]],
        prompt_template: Optional[str] = None,
    ):
        """Initialize the summarizer.

        Args:
            llm: Async callable with signature (prompt, schema) -> Dict.
                 Use functools.partial to bind level/timeout if needed.
            prompt_template: Optional custom prompt template. Should include
                            {query} and {results} placeholders.
        """
        self._llm = llm
        self._prompt_template = prompt_template or self.DEFAULT_PROMPT_TEMPLATE

    def format_results(self, results: List[Dict]) -> str:
        """Format results list into text for the prompt.

        Args:
            results: List of result dictionaries with 'name' and 'description' keys.
                    Caller should slice to desired length before calling.

        Returns:
            Formatted string with numbered results.
        """
        results_text = []
        for i, result in enumerate(results, 1):
            name = result.get("name", "Unknown")
            description = result.get("description", "")
            results_text.append(f"{i}. {name}: {description}")
        return "\n".join(results_text)

    def build_prompt(self, query: str, results: List[Dict]) -> str:
        """Build the full prompt for summarization.

        Args:
            query: The user's query text.
            results: List of result dictionaries.

        Returns:
            Formatted prompt string ready for the LLM.
        """
        results_text = self.format_results(results)
        return self._prompt_template.format(query=query, results=results_text)

    async def summarize(
        self, query: str, results: List[Dict]
    ) -> Optional[SummaryResult]:
        """Generate a summary of the search results.

        Args:
            query: The user's query text.
            results: List of result dictionaries to summarize.
                    Caller should slice to desired length before calling.

        Returns:
            SummaryResult if successful, None if no results or LLM fails.
        """
        if not results:
            return None

        prompt = self.build_prompt(query, results)

        try:
            response = await self._llm(prompt, self.SCHEMA)
        except Exception:
            return None

        if response and "summary" in response:
            return SummaryResult(summary=response["summary"], raw_response=response)

        return None


def create_default_summarizer() -> ResultsSummarizer:
    """Factory function to create a summarizer with the default ask_llm.

    Returns:
        ResultsSummarizer configured with the production ask_llm function.
    """
    from nlweb_core.llm import ask_llm

    llm = partial(ask_llm, level="high", timeout=20)
    return ResultsSummarizer(llm=llm)
