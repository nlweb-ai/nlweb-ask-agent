"""
Intent detection for site-specific queries using LLM scoring.
"""

import logging
from typing import List, Dict, Any
from nlweb_core.config import get_config
from nlweb_core.scoring import get_scoring_provider, ScoringContext

logger = logging.getLogger(__name__)


class IntentDetector:
    """
    Detects which intents match a given query using LLM scoring model.
    Uses score-based detection: score >= 70 = match.
    """

    # Score threshold for intent match (0-100 scale - Pi Labs provider multiplies by 100)
    INTENT_MATCH_THRESHOLD = 70

    def __init__(self):
        """
        Initialize IntentDetector.
        Uses scoring LLM model from CONFIG via ask_llm_parallel.
        """
        logger.info("IntentDetector initialized (uses scoring LLM model)")

    def _get_default_intent_prompt(self, intent_value: str) -> str:
        """
        Generate default intent detection prompt from value.

        Args:
            intent_value: Intent value (e.g., "restaurant_search")

        Returns:
            Default prompt string
        """
        # Replace underscores with spaces for readability
        readable_value = intent_value.replace('_', ' ')
        return f"Does the query have the intent specified: {readable_value}?"

    async def detect_intents(
        self,
        query: str,
        intent_elicitations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Detect which intents match the query using score-based detection.

        Uses flattened structure where each pair has one required_info.
        Deduplicates intents to avoid checking the same intent multiple times.

        Args:
            query: User's query text
            intent_elicitations: List of intent-required_info pairs from config
                Format: [{"intent": {...}, "required_info": {...}}, ...]

        Returns:
            List of required_info configs from matching intents (includes universal checks)
        """
        matching_required_info = []

        logger.debug(
            f"Detecting intents for query: '{query}' "
            f"({len(intent_elicitations)} intent-required_info pairs)"
        )

        # Group pairs by intent value to deduplicate
        # Format: {intent_value: [(idx, intent_obj, required_info_obj), ...]}
        intent_groups: Dict[str, List[tuple]] = {}
        universal_required_info = []  # For empty intents

        for idx, item in enumerate(intent_elicitations):
            intent = item.get("intent", {})
            required_info = item.get("required_info", {})

            # Empty intent = universal (applies to ALL queries)
            if not intent or not intent.get("value"):
                logger.debug(f"Pair #{idx}: Universal (empty intent) - always matches")
                universal_required_info.append(required_info)
                continue

            # Group by intent value
            intent_value = intent["value"]
            if intent_value not in intent_groups:
                intent_groups[intent_value] = []
            intent_groups[intent_value].append((idx, intent, required_info))

        # Add all universal required_info (no intent check needed)
        matching_required_info.extend(universal_required_info)

        # Batch check unique intents using LLM scoring
        if intent_groups:
            # Prepare batch contexts for scoring provider
            contexts = []
            unique_intents = []  # Track order: [(intent_value, required_info_list)]

            for intent_value, pairs in intent_groups.items():
                # Build ScoringContext for scoring provider
                contexts.append(ScoringContext(
                    query=query,
                    intent=intent_value
                ))

                # Collect all required_info for this intent
                required_info_list = [required_info for _, _, required_info in pairs]
                unique_intents.append((intent_value, required_info_list))

            logger.debug(
                f"Checking {len(unique_intents)} unique intents "
                f"(deduplicated from {len(intent_elicitations)} pairs)"
            )

            # Call scoring provider in batch with standard question
            scoring_question = "Does the query match this intent?"
            try:
                provider = get_scoring_provider()
                scoring_config = get_config().scoring_llm_model
                if not scoring_config:
                    logger.warning("No scoring_llm_model configured, skipping intent detection")
                    return matching_required_info
                results = await provider.score_batch(
                    scoring_question,
                    contexts,
                    timeout=8,
                    api_key=scoring_config.api_key,
                    endpoint=scoring_config.endpoint,
                )

                # Process results (scores are now floats directly)
                for i, (intent_value, required_info_list) in enumerate(unique_intents):
                    result = results[i] if i < len(results) else None
                    # Handle exceptions or missing results
                    if result is None or isinstance(result, BaseException):
                        logger.warning(f"Intent '{intent_value}' scoring failed: {result}")
                        continue
                    score = result  # score is now a float directly

                    if score >= self.INTENT_MATCH_THRESHOLD:
                        logger.debug(
                            f"Intent '{intent_value}' MATCHED "
                            f"(score: {score} >= {self.INTENT_MATCH_THRESHOLD}), "
                            f"adding {len(required_info_list)} required_info items"
                        )
                        # Add all required_info for this matching intent
                        matching_required_info.extend(required_info_list)
                    else:
                        logger.debug(
                            f"Intent '{intent_value}' did not match "
                            f"(score: {score} < {self.INTENT_MATCH_THRESHOLD})"
                        )

            except Exception as e:
                logger.error(
                    f"Error during batch intent detection: {e}",
                    exc_info=True
                )
                # On error, don't block - just skip these intents

        logger.info(
            f"Intent detection complete: {len(matching_required_info)} "
            f"required_info items from matching intents"
        )

        return matching_required_info
