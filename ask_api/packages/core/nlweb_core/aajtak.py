# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Aajtak-specific AskHandler with Hindi/Hinglish transliteration support.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from nlweb_core.config import get_config, override_scoring_provider
from nlweb_core.handler import AskHandler, OutputMethod
from nlweb_core.protocol.models import AskRequest
from nlweb_core.query_analysis.query_analysis import (
    DefaultQueryAnalysisHandler,
    query_analysis_tree,
)
from nlweb_core.request_context import set_request_id
from nlweb_core.site_config import get_elicitation_handler

logger = logging.getLogger(__name__)


class AajtakAskHandler(AskHandler):
    """Handler for aajtak.in with Hindi/Hinglish transliteration support."""

    request_id: str
    is_seeking_recent_info: bool = False

    def __init__(self, **kwargs) -> None:
        """Initialize the handler with a unique request ID."""
        self.request_id = set_request_id()

    async def do(
        self,
        ask_request: AskRequest,
        output_method: OutputMethod,
    ) -> None:
        """
        Process the ask request using the NLWeb RAG pipeline with Hindi support.

        Main query execution flow:
        1. Prepare query (decontextualization with transliteration, analysis, elicitation check)
        2. Send metadata (with correct response_type)
        3. Execute query body OR send elicitation
        4. Post-process results
        """
        # Build site_config with item_type for use throughout the query
        site_config_lookup = get_config().get_site_config_lookup("default")
        item_type = None
        if site_config_lookup and ask_request.query.site:
            item_types = await site_config_lookup.get_config_type(
                ask_request.query.site, "item_types"
            )
            if item_types and isinstance(item_types, list) and len(item_types) > 0:
                item_type = item_types[0]

        site_config: dict[str, str] = {"item_type": item_type if item_type else "item"}

        # Prepare first to determine if elicitation is needed
        ask_request.query.decontextualized_query = await self._decontextualize_query(
            ask_request, site_config
        )

        if (elicitation_data := await self._check_elicitation(ask_request)) is not None:
            await self._send_meta(
                output_method, "Elicitation", ask_request.query.effective_query
            )
            if output_method:
                await output_method({"elicitation": elicitation_data})
            return

        # Intentionally passing decontextualized query, or None if not.
        await self._send_meta(
            output_method, "Answer", ask_request.query.decontextualized_query
        )
        final_ranked_answers = await self._run_query_body(
            ask_request, output_method, site_config
        )
        await self._post_results(ask_request, output_method, final_ranked_answers)

    async def _run_query_body(
        self,
        request: AskRequest,
        output_method: OutputMethod,
        site_config: dict[str, str],
    ) -> list[dict]:
        """
        Execute the query body with dual-query strategy.

        Process (SAME for both query types):
        1. Retrieve fresh (≤5 days) + regular results in parallel
        2. Merge and deduplicate
        3. Enrich with object storage
        4. Rank all together with LLM scorer and apply threshold
        5. If seeking recent info: reorder into fresh-first bins (maintaining score order within bins)
        """
        from nlweb_core.ranking import Ranking
        from nlweb_core.retriever import enrich_results_from_object_storage

        config = get_config()
        vectordb_client = config.get_retrieval_provider("default")

        # Dual-query strategy: regular + fresh results
        # Optimize to avoid scoring too many items:
        # - Fresh: 40% of requested results (prioritized for recency)
        # - Regular: 60% of requested results (broader relevance)
        fresh_proportion = 0.4
        fresh_count = int(request.query.num_results * fresh_proportion)
        regular_count = request.query.num_results - fresh_count

        five_days_ago = datetime.now(timezone.utc) - timedelta(days=5)
        date_filter = f"datePublished ge {five_days_ago.isoformat()}"

        # Execute regular + fresh queries in parallel
        regular_items, fresh_items = await asyncio.gather(
            vectordb_client.search(
                request.query.effective_query,
                request.query.site,
                regular_count,
            ),
            vectordb_client.search(
                request.query.effective_query,
                request.query.site,
                fresh_count,
                date_filter=date_filter,
            ),
        )

        # Merge: deduplicate by URL, prioritize fresh items at top
        retrieved_items = self._merge_results(fresh_items, regular_items)
        logger.info(
            f"Dual-query results: {len(fresh_items)} fresh + {len(regular_items)} regular → {len(retrieved_items)} merged (target: {fresh_count}+{regular_count})"
        )

        if config.object_storage_providers:
            object_lookup_client = config.get_object_lookup_provider("default")
            retrieved_items = await enrich_results_from_object_storage(
                retrieved_items, object_lookup_client
            )

        # Rank all results together with LLM scorer and apply threshold
        with override_scoring_provider("default", "4.1-mini"):
            final_ranked_answers = await Ranking().rank(
                items=retrieved_items,
                query_text=request.query.effective_query,
                item_type=site_config["item_type"],
                max_results=request.query.max_results,
                min_score=request.query.min_score,
                site=request.query.site,
            )

        # If seeking recent info, reorder into fresh-first bins (fresh ≤5 days, old >5 days)
        if self.is_seeking_recent_info:
            logger.info(
                f"Query classified as seeking recent info - reordering results with fresh items first"
            )
            final_ranked_answers = self._reorder_by_recency(final_ranked_answers, five_days_ago)
        else:
            logger.info(
                f"Query classified as about specific event - returning results sorted by relevance only"
            )

        await self._send_results(output_method, final_ranked_answers)
        return final_ranked_answers

    def _merge_results(self, fresh_items: list, regular_items: list) -> list:
        """
        Merge fresh and regular results, deduplicating by URL.
        Fresh items are prioritized at the top.
        """
        seen_urls = set()
        merged = []

        # Add fresh items first
        for item in fresh_items:
            if item.url not in seen_urls:
                merged.append(item)
                seen_urls.add(item.url)

        # Add regular items that aren't duplicates
        for item in regular_items:
            if item.url not in seen_urls:
                merged.append(item)
                seen_urls.add(item.url)

        return merged

    def _reorder_by_recency(self, results: list[dict], cutoff_date: datetime) -> list[dict]:
        """
        Reorder results into two bins: fresh (≤5 days) first, then old (>5 days).
        Within each bin, maintain score-based ordering from ranking.

        Args:
            results: Scored and filtered results sorted by relevance
            cutoff_date: Datetime cutoff for "fresh" (5 days ago)

        Returns:
            Reordered results with fresh items first, old items second
        """
        from email.utils import parsedate_to_datetime

        fresh_bin = []
        old_bin = []

        for result in results:
            date_published_str = result.get("datePublished")
            if date_published_str:
                try:
                    # Try RFC 2822 format first (e.g., "Wed, 04 Feb 2026 23:14:46 +0530")
                    date_published = parsedate_to_datetime(date_published_str)
                except (ValueError, TypeError):
                    try:
                        # Fallback to ISO format (e.g., "2026-02-04T23:14:46+05:30")
                        date_published = datetime.fromisoformat(date_published_str.replace('Z', '+00:00'))
                    except (ValueError, AttributeError) as e:
                        logger.warning(f"Failed to parse datePublished '{date_published_str}': {e}")
                        # If parsing fails, put in old bin
                        old_bin.append(result)
                        continue

                # Ensure timezone-aware comparison
                if date_published.tzinfo is None:
                    date_published = date_published.replace(tzinfo=timezone.utc)

                if date_published >= cutoff_date:
                    fresh_bin.append(result)
                else:
                    old_bin.append(result)
            else:
                # No date, put in old bin
                old_bin.append(result)

        logger.info(
            f"Recency reordering: {len(fresh_bin)} fresh (≤5 days) + {len(old_bin)} old (>5 days) = {len(results)} total"
        )

        return fresh_bin + old_bin

    async def _decontextualize_query(
        self,
        request: AskRequest,
        site_config: dict[str, str],
    ) -> str | None:
        """
        Decontextualize query for Hindi sites with Hinglish transliteration and recency classification.
        Uses Hindi-specific prompts that handle romanized Hindi (Hinglish) conversion and classify
        whether the query is seeking recent information.

        Args:
            request: The ask request containing query and context.
            site_config: Site configuration dict with 'item_type' key.

        Returns:
            The decontextualized query string (transliterated if needed), or None if no context.

        Side Effects:
            Sets self.is_seeking_recent_info based on the LLM classification.
        """
        context = request.context
        prev_queries = (context.prev or []) if context else []
        context_text = context.text if context else None

        if not prev_queries and context_text is None:
            # No context - transliterate with recency classification
            result = await DefaultQueryAnalysisHandler(
                request,
                prompt_ref="NoContextTransliteratorWithRecency",
                root_node=query_analysis_tree,
                site_config=site_config,
            ).do()
            if result:
                self.is_seeking_recent_info = result.get("is_seeking_recent_info", False)
                return result.get("decontextualized_query")
            return None
        elif prev_queries and context_text is None:
            # Decontextualize with prev queries + transliteration + recency classification
            result = await DefaultQueryAnalysisHandler(
                request,
                prompt_ref="PrevQueryDecontextualizerHindiWithRecency",
                root_node=query_analysis_tree,
                site_config=site_config,
            ).do()
            if result:
                self.is_seeking_recent_info = result.get("is_seeking_recent_info", False)
                return result.get("decontextualized_query")
            return None
        else:
            # Decontextualize with full context + transliteration + recency classification
            result = await DefaultQueryAnalysisHandler(
                request,
                prompt_ref="FullContextDecontextualizerHindiWithRecency",
                root_node=query_analysis_tree,
                site_config=site_config,
            ).do()
            if result:
                self.is_seeking_recent_info = result.get("is_seeking_recent_info", False)
                return result.get("decontextualized_query")
            return None

    async def _check_elicitation(self, request: AskRequest) -> dict | None:
        """
        Check if elicitation is needed for this query.
        This is called after decontextualization and query analysis.

        Args:
            request: The ask request to check.

        Returns:
            Elicitation data dict if elicitation is needed, None otherwise.
        """
        site_config_lookup = get_config().get_site_config_lookup("default")
        if not site_config_lookup or not request.query.site:
            return None

        site_config = await site_config_lookup.get_config_type(
            request.query.site, "elicitation"
        )
        if not site_config:
            return None

        elicitation_handler = get_elicitation_handler()
        if not elicitation_handler:
            logger.debug("Elicitation handler not initialized - skipping elicitation")
            return None

        try:
            elicitation_prompt = await elicitation_handler.evaluate_query(
                query_text=request.query.effective_query,
                site_config=site_config,
            )
            if elicitation_prompt:
                logger.info("Elicitation needed for query")
                return elicitation_prompt
        except Exception as e:
            logger.error(f"Error during elicitation evaluation: {e}", exc_info=True)
            raise

        return None

    async def _send_meta(
        self,
        output_method: OutputMethod,
        response_type: str,
        decontextualized_query: str | None = None,
    ) -> None:
        """Send the metadata object via the output method."""
        if output_method:
            meta: dict[str, str] = {
                "version": "0.54",
                "response_type": response_type,
                "request_id": self.request_id,
            }
            if decontextualized_query:
                meta["decontextualized_query"] = decontextualized_query
            await output_method({"_meta": meta})

    async def _send_results(
        self,
        output_method: OutputMethod,
        results: list[dict],
    ) -> None:
        """
        Send v0.54 compliant results array.

        Args:
            output_method: The callback for sending results.
            results: List of result objects (dicts with @type, name, etc.)
        """
        if output_method:
            await output_method({"results": results})

    async def _post_results(
        self,
        request: AskRequest,
        output_method: OutputMethod,
        final_ranked_answers: list[dict],
    ) -> None:
        """Execute post-query processing (summarization, conversation storage, etc.)."""
        from nlweb_core.conversation_saver import ConversationSaver
        from nlweb_core.postQueryProcessing import PostQueryProcessing

        prefer = request.prefer
        await PostQueryProcessing(site=request.query.site).process(
            final_ranked_answers=final_ranked_answers,
            query_text=request.query.effective_query,
            modes=[
                m.strip()
                for m in (prefer.mode if prefer and prefer.mode else "list").split(",")
            ],
            send_results=lambda results: self._send_results(output_method, results),
        )

        await ConversationSaver().save(request, final_ranked_answers)
