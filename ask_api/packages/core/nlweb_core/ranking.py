# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
This file contains the code for the ranking stage.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

from __future__ import annotations

import logging

from nlweb_core.config import get_config, RankingConfig
from nlweb_core.item_retriever import RetrievedItem
from nlweb_core.protocol.models import Query
from nlweb_core.llm_exceptions import (
    LLMError,
    LLMTimeoutError,
    LLMRateLimitError,
    LLMConnectionError,
)
from nlweb_core.ranked_result import RankedResult
from nlweb_core.scoring import get_scoring_provider, ScoringContext
from nlweb_core.utils import trim_json

logger = logging.getLogger(__name__)


class Ranking:

    def __init__(self) -> None:
        pass

    async def rank(
        self,
        items: list[RetrievedItem],
        query_text: str,
        item_type: str,
        max_results: int,
        min_score: int,
    ) -> list[dict]:
        """
        Rank retrieved items by relevance to the query.

        Args:
            items: List of retrieved items to rank
            query_text: The query text to rank against
            item_type: Type of items being ranked (for scoring context)
            max_results: Maximum number of results to return
            min_score: Minimum score threshold for filtering results

        Returns:
            List of ranked result dicts, sorted by score descending
        """
        if not items:
            return []

        # Build ScoringContext objects directly
        contexts = [
            ScoringContext(
                query=query_text,
                item_description=str(trim_json(item.schema_object)),
                item_type=item_type,
            )
            for item in items
        ]

        # Get config and scoring question
        config = get_config()
        ranking_config = config.ranking or RankingConfig()
        scoring_question = ranking_config.scoring_question

        try:
            # Get the scoring provider and score all items in batch
            provider = get_scoring_provider()
            scoring_config = config.scoring_llm_model
            if not scoring_config:
                raise ValueError("No scoring_llm_model configured")
            scores = await provider.score_batch(
                [scoring_question],
                contexts,
                timeout=8,
                api_key=scoring_config.api_key,
                endpoint=scoring_config.endpoint,
            )
        except Exception as e:
            logger.error(f"Ranking failed: {e}", exc_info=True)
            raise

        # Process results
        ranked_answers: list[RankedResult] = []
        for score, item in zip(scores, items):

            # Handle exceptions from score_batch
            if isinstance(score, BaseException):
                if isinstance(score, LLMTimeoutError):
                    logger.warning(f"LLM timeout ranking {item.url}: {score}")
                elif isinstance(score, LLMRateLimitError):
                    logger.warning(f"LLM rate limit hit ranking {item.url}: {score}")
                elif isinstance(score, LLMConnectionError):
                    logger.warning(f"LLM connection error ranking {item.url}: {score}")
                elif isinstance(score, LLMError):
                    logger.error(
                        f"LLM error ranking {item.url}: {score}", exc_info=True
                    )
                    if config.should_raise_exceptions():
                        raise score
                else:
                    logger.error(
                        f"Ranking failed for {item.url}: {score}", exc_info=True
                    )
                    if config.should_raise_exceptions():
                        raise score
                continue

            # Create RankedResult
            result = RankedResult(item=item, score=int(score))
            ranked_answers.append(result)

        # Filter and sort by score
        filtered = [r for r in ranked_answers if r.score > min_score]
        ranked = sorted(filtered, key=lambda x: x.score, reverse=True)

        # Convert to dicts for consumer compatibility
        return [r.to_dict() for r in ranked[:max_results]]
