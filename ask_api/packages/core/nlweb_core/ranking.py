# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
This file contains the code for the ranking stage.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

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


def _extract_date_published(schema_object: list[dict]) -> str | None:
    """
    Extract datePublished from schema.org object.

    Args:
        schema_object: List of schema.org dicts (from RetrievedItem.schema_object)

    Returns:
        datePublished string if found, None otherwise
    """
    if not schema_object or not isinstance(schema_object, list):
        return None

    for obj in schema_object:
        if isinstance(obj, dict) and "datePublished" in obj:
            return obj["datePublished"]

    return None


def _parse_date_published(date_str: str | None) -> datetime | None:
    """
    Parse datePublished string to datetime.

    Handles multiple formats:
    - RFC 2822: "Sun, 01 Oct 2023 16:18:16 +0530"
    - ISO 8601: "2023-10-01T16:18:16+05:30"

    Args:
        date_str: Date string from schema.org datePublished

    Returns:
        datetime object with timezone, or None if parsing fails
    """
    if not date_str:
        return None

    try:
        # Try RFC 2822 format first (most common from crawler)
        return parsedate_to_datetime(date_str)
    except Exception:
        pass

    try:
        # Try ISO 8601 format
        return datetime.fromisoformat(date_str)
    except Exception:
        pass

    logger.warning(f"Failed to parse datePublished: {date_str}")
    return None


def _calculate_age_days(pub_date: datetime | None) -> int | None:
    """
    Calculate age in days from publication date.

    Args:
        pub_date: Publication datetime with timezone

    Returns:
        Age in days (rounded down), or None if pub_date is None
    """
    if not pub_date:
        return None

    now = datetime.now(timezone.utc)
    age = now - pub_date
    return int(age.total_seconds() / 86400)  # Convert to days


def _apply_recency_boost(
    score: float, age_days: int | None, recency_config: dict | None
) -> float:
    """
    Apply site-specific recency boost to LLM score.

    Hybrid scoring formula:
    final_score = (llm_score * llm_weight) + (recency_score * recency_weight)
    where llm_weight = 1 - recency_weight

    Recency score uses exponential decay:
    recency_score = 100 * exp(-decay_rate * age_days / 100)

    Args:
        score: LLM score (0-100)
        age_days: Age in days since publication
        recency_config: Site-specific recency configuration with:
            - enabled: bool (default False)
            - recency_weight: float (default 0.15, range 0-1)
            - decay_rate: float (default 0.1, controls how fast recency decays)
            - max_age_days: int (default 365, items older than this get 0 recency score)

    Returns:
        Boosted score (0-100)
    """
    # Default configuration values
    DEFAULT_RECENCY_WEIGHT = 0.15  # Sensible default for news sites
    DEFAULT_DECAY_RATE = 0.1
    DEFAULT_MAX_AGE_DAYS = 365

    if not recency_config or not recency_config.get("enabled", False):
        return score

    if age_days is None or age_days < 0:
        return score

    # Get configuration with defaults
    recency_weight = recency_config.get("recency_weight", DEFAULT_RECENCY_WEIGHT)
    decay_rate = recency_config.get("decay_rate", DEFAULT_DECAY_RATE)
    max_age_days = recency_config.get("max_age_days", DEFAULT_MAX_AGE_DAYS)

    # Clamp recency_weight to valid range
    recency_weight = max(0.0, min(1.0, recency_weight))

    # Calculate llm_weight (ensures they sum to 1.0)
    llm_weight = 1.0 - recency_weight

    # Clamp age to max_age_days
    effective_age = min(age_days, max_age_days)

    # Calculate recency score with exponential decay
    import math

    recency_score = 100 * math.exp(-decay_rate * effective_age / 100)

    # Hybrid score
    boosted = (score * llm_weight) + (recency_score * recency_weight)

    # Clamp to 0-100
    return max(0, min(100, boosted))


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
        start_num: int = 0,
        site: str = "all"
    ) -> list[dict]:
        """
        Rank retrieved items by relevance to the query with freshness-aware scoring.

        Args:
            items: List of retrieved items to rank
            query_text: The query text to rank against
            item_type: Type of items being ranked (for scoring context)
            max_results: Maximum number of results to return
            min_score: Minimum score threshold for filtering results
            site: Site filter for site-specific recency boost configuration

        Returns:
            List of ranked result dicts, sorted by score descending
        """
        if not items:
            return []

        # Check if freshness is enabled for this site (controls both LLM awareness and boost)
        recency_config = None
        freshness_enabled = False
        if site and site != "all":
            try:
                from nlweb_core.site_config import get_site_config_lookup

                site_config_lookup = get_site_config_lookup("default")
                if site_config_lookup:
                    freshness_config = await site_config_lookup.get_config_type(
                        site, "freshness_config"
                    )
                    if freshness_config:
                        recency_config = freshness_config.get("recency_boost")
                        if recency_config and recency_config.get("enabled", False):
                            freshness_enabled = True
                            logger.debug(
                                f"Freshness enabled for {site}: {recency_config}"
                            )
            except Exception as e:
                logger.warning(f"Failed to load freshness config for {site}: {e}")

        # Extract publication dates ONLY if freshness is enabled
        # This controls both LLM awareness (via prompt) and algorithmic boost
        date_info = []
        if freshness_enabled:
            for item in items:
                date_str = _extract_date_published(item.schema_object)
                pub_date = _parse_date_published(date_str)
                age_days = _calculate_age_days(pub_date)
                date_info.append((date_str, age_days))
        else:
            # No freshness - use None for all items
            date_info = [(None, None) for _ in items]

        # Build ScoringContext objects (with or without freshness info based on config)
        contexts = [
            ScoringContext(
                query=query_text,
                item_description=str(trim_json(item.schema_object)),
                item_type=item_type,
                publication_date=date_str,  # None if freshness disabled
                age_days=age_days,  # None if freshness disabled
            )
            for item, (date_str, age_days) in zip(items, date_info)
        ]

        # Get config and scoring questions
        config = get_config()
        ranking_config = config.ranking or RankingConfig()
        scoring_questions = ranking_config.scoring_questions

        try:
            # Get the scoring provider and score all items in batch
            provider = get_scoring_provider("default")
            scores = await provider.score_batch(
                scoring_questions,
                contexts,
                timeout=8,
            )
        except Exception as e:
            logger.error(f"Ranking failed: {e}", exc_info=True)
            raise

        # Process results
        ranked_answers: list[RankedResult] = []
        for score, item, (date_str, age_days) in zip(scores, items, date_info):

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

            # Apply site-specific recency boost
            boosted_score = _apply_recency_boost(score, age_days, recency_config)

            if boosted_score != score:
                logger.debug(
                    f"Recency boost applied for {item.url}: "
                    f"LLM={score:.1f}, boosted={boosted_score:.1f}, age={age_days}d"
                )

            # Create RankedResult with boosted score
            result = RankedResult(item=item, score=int(boosted_score))
            ranked_answers.append(result)

        # Filter and sort by score
        filtered = [r for r in ranked_answers if r.score > min_score]
        ranked = sorted(filtered, key=lambda x: x.score, reverse=True)

        # Convert to dicts for consumer compatibility
        last_index = start_num + max_results
        print("Start number is", start_num)
        # Handle pagination
        return [r.to_dict() for r in ranked[start_num:last_index]]
