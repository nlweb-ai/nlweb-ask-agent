# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
This file contains the NLWebHandler class for query processing.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""
import logging
from typing import Callable, Awaitable
from nlweb_core.query_analysis.query_analysis import (
    DefaultQueryAnalysisHandler,
    QueryAnalysisHandler,
    query_analysis_tree,
)
from nlweb_core.protocol.models import AskRequest
from nlweb_core.request_context import set_request_id
from nlweb_core.site_config import get_site_config_lookup, get_elicitation_handler

logger = logging.getLogger(__name__)


class NLWebHandler:

    def __init__(
        self,
        ask_request: AskRequest,
        output_method: Callable[[dict], Awaitable[None]] | None,
    ):
        self.request_id = set_request_id()
        self.output_method = output_method
        self.request = ask_request

    async def runQuery(self):
        """
        Main query execution flow:
        1. Prepare query (decontextualization, analysis, elicitation check)
        2. Send metadata (with correct response_type)
        3. Execute query body OR send elicitation
        4. Post-process results
        """
        # Build site_config with item_type for use throughout the query
        site_config_lookup = get_site_config_lookup()
        if site_config_lookup:
            item_type = site_config_lookup.get_item_type_for_ranking(
                self.request.query.site
            )
        else:
            item_type = None

        site_config = {"item_type": item_type if item_type else "item"}

        # Prepare first to determine if elicitation is needed
        self.request.query.decontextualized_query = await self.decontextualize_query(
            site_config
        )
        # Note: query_analysis_results is not in use yet
        # so it is commented out to avoid unnecessary processing.
        # query_analysis_results = (
        #    await QueryAnalysisHandler(self.request, site_config=site_config).do() or {}
        # )
        if (elicitation_data := await self._check_elicitation()) is not None:
            await self.send_meta("Elicitation", self.request.query.effective_query)
            if self.output_method:
                await self.output_method({"elicitation": elicitation_data})
            return

        # Intentionally passing decontextualized query, or None if not.
        await self.send_meta("Answer", self.request.query.decontextualized_query)
        final_ranked_answers = await self.runQueryBody(site_config)
        await self.postResults(final_ranked_answers)

    async def runQueryBody(self, site_config: dict) -> list[dict]:
        """Execute the query body by retrieving and ranking items."""
        from nlweb_core.retriever import get_item_retriever
        from nlweb_core.item_retriever import RetrievalParams
        from nlweb_core.ranking import Ranking

        retriever = get_item_retriever()
        retrieved_items = await retriever.retrieve(
            RetrievalParams(
                query_text=self.request.query.effective_query,
                site=self.request.query.site,
                num_results=self.request.query.num_results,
            )
        )

        final_ranked_answers = await Ranking().rank(
            items=retrieved_items,
            query_text=self.request.query.effective_query,
            item_type=site_config["item_type"],
            max_results=self.request.query.num_results,
            min_score=self.request.query.min_score,
        )

        await self.send_results(final_ranked_answers)
        return final_ranked_answers

    async def decontextualize_query(self, site_config: dict) -> str | None:
        """
        Decontextualize the query using conversation context.

        Args:
            site_config: Site configuration dict with 'item_type' key.

        Returns:
            The decontextualized query string, or None if no context was provided.
        """
        # TODO: Handle transliteration via site configuration
        # Route to language-specific decontextualization if needed
        if self.request.query.site == "aajtak.in":
            return await self._decontextualize_query_hindi(site_config)

        # Standard decontextualization for non-transliteration sites
        context = self.request.context
        prev_queries = (context.prev or []) if context else []
        context_text = context.text if context else None

        if not prev_queries and context_text is None:
            return None
        elif prev_queries and context_text is None:
            result = await DefaultQueryAnalysisHandler(
                self.request,
                prompt_ref="PrevQueryDecontextualizer",
                root_node=query_analysis_tree,
                site_config=site_config,
            ).do()
            return result.get("decontextualized_query") if result else None
        else:
            result = await DefaultQueryAnalysisHandler(
                self.request,
                prompt_ref="FullContextDecontextualizer",
                root_node=query_analysis_tree,
                site_config=site_config,
            ).do()
            return result.get("decontextualized_query") if result else None

    async def _decontextualize_query_hindi(self, site_config: dict) -> str | None:
        """
        Decontextualize query for Hindi sites with Hinglish transliteration.
        Uses Hindi-specific prompts that handle romanized Hindi (Hinglish) conversion.

        Args:
            site_config: Site configuration dict with 'item_type' key.

        Returns:
            The decontextualized query string (transliterated if needed), or None if no context.
        """
        context = self.request.context
        prev_queries = (context.prev or []) if context else []
        context_text = context.text if context else None

        if not prev_queries and context_text is None:
            # No context - just transliterate
            result = await DefaultQueryAnalysisHandler(
                self.request,
                prompt_ref="NoContextTransliterator",
                root_node=query_analysis_tree,
                site_config=site_config,
            ).do()
            return result.get("transliterated_query") if result else None
        elif prev_queries and context_text is None:
            # Decontextualize with prev queries + transliteration
            result = await DefaultQueryAnalysisHandler(
                self.request,
                prompt_ref="PrevQueryDecontextualizerHindi",
                root_node=query_analysis_tree,
                site_config=site_config,
            ).do()
            return result.get("decontextualized_query") if result else None
        else:
            # Decontextualize with full context + transliteration
            result = await DefaultQueryAnalysisHandler(
                self.request,
                prompt_ref="FullContextDecontextualizerHindi",
                root_node=query_analysis_tree,
                site_config=site_config,
            ).do()
            return result.get("decontextualized_query") if result else None

    async def _check_elicitation(self) -> dict | None:
        """
        Check if elicitation is needed for this query.
        This is called after decontextualization and query analysis.

        Returns:
            Elicitation data dict if elicitation is needed, None otherwise.
        """
        site_config_lookup = get_site_config_lookup()
        if not site_config_lookup:
            return None

        site_config = site_config_lookup.get_config_for_site_filter(
            self.request.query.site
        )
        if not site_config:
            return None

        elicitation_handler = get_elicitation_handler()
        if not elicitation_handler:
            logger.debug("Elicitation handler not initialized - skipping elicitation")
            return None

        try:
            elicitation_prompt = await elicitation_handler.evaluate_query(
                query_text=self.request.query.effective_query,
                site_config=site_config,
            )
            if elicitation_prompt:
                logger.info("Elicitation needed for query")
                return elicitation_prompt
        except Exception as e:
            logger.error(f"Error during elicitation evaluation: {e}", exc_info=True)

        return None

    async def send_meta(
        self, response_type: str, decontextualized_query: str | None = None
    ):
        """Send the metadata object via the output method."""
        if self.output_method:
            meta = {
                "version": "0.54",
                "response_type": response_type,
                "request_id": self.request_id,
            }
            if decontextualized_query:
                meta["decontextualized_query"] = decontextualized_query
            await self.output_method({"_meta": meta})

    async def send_results(self, results: list):
        """
        Send v0.54 compliant results array.

        Args:
            results: List of result objects (dicts with @type, name, etc.)
        """
        if self.output_method:
            await self.output_method({"results": results})

    async def postResults(self, final_ranked_answers: list[dict]):
        """Execute post-query processing (summarization, conversation storage, etc.)."""
        from nlweb_core.conversation_saver import ConversationSaver
        from nlweb_core.postQueryProcessing import PostQueryProcessing

        prefer = self.request.prefer
        await PostQueryProcessing().process(
            final_ranked_answers=final_ranked_answers,
            query_text=self.request.query.effective_query,
            modes=[
                m.strip()
                for m in (prefer.mode if prefer and prefer.mode else "list").split(",")
            ],
            send_results=self.send_results,
        )

        await ConversationSaver().save(self.request, final_ranked_answers)
