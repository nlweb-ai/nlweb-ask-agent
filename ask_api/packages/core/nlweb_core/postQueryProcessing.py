# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Post-query processing for NLWeb handlers.
Handles summarization and other post-ranking tasks.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

from typing import Awaitable, Callable, Optional

from nlweb_core.summarizer import (
    ResultsSummarizer,
    create_default_summarizer,
    create_hindi_summarizer,
)


class PostQueryProcessing:
    """Post-processing after ranking is complete."""

    def __init__(
        self, summarizer: Optional[ResultsSummarizer] = None, site: Optional[str] = None
    ):
        """Initialize post-query processing.

        Args:
            summarizer: Optional ResultsSummarizer instance. If not provided,
                       a site-appropriate summarizer will be created.
            site: Site domain (e.g., 'aajtak.in'). Used to select language-specific
                 summarizer if no custom summarizer is provided.
        """
        if summarizer:
            self._summarizer = summarizer
        elif site == "aajtak.in":
            self._summarizer = create_hindi_summarizer()
        else:
            self._summarizer = create_default_summarizer()

    async def process(
        self,
        final_ranked_answers: list[dict],
        query_text: str,
        modes: list[str],
        send_results: Callable[[list], Awaitable[None]],
        start_num: int = 0,
    ) -> None:
        """Execute post-query processing based on mode.

        Args:
            final_ranked_answers: The ranked search results.
            query_text: The query text (decontextualized or original).
            modes: List of processing modes (e.g., ['list', 'summarize']).
            send_results: Async callback to send results to the client.
        """
        if "summarize" in modes:
            await self._summarize_results(
                final_ranked_answers, query_text, send_results, start_num
            )

    async def _summarize_results(
        self,
        results: list[dict],
        query_text: str,
        send_results: Callable[[list], Awaitable[None]],
        start_num: int = 0,
    ) -> None:
        """Generate and send a summary of the top results."""
        if not results:
            return

        summary_result = await self._summarizer.summarize(
            query=query_text, results=results[:3], start_num=start_num
        )

        if summary_result:
            await send_results([summary_result.to_result_object()])
