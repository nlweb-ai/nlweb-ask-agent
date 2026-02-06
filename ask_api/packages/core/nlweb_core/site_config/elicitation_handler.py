"""
Main elicitation handler that orchestrates the complete elicitation flow.
"""

import logging
from typing import Any, Dict, Optional

from .elicitation_checker import ElicitationChecker
from .intent_detector import IntentDetector

logger = logging.getLogger(__name__)


class ElicitationHandler:
    """
    Orchestrates the elicitation flow:
    1. Detect matching intents from site config
    2. Check for missing information
    3. Generate follow-up prompt if needed
    """

    def __init__(self):
        """Initialize ElicitationHandler."""
        self.intent_detector = IntentDetector()
        self.elicitation_checker = ElicitationChecker()

        logger.info(
            "ElicitationHandler initialized (uses scoring LLM via ask_llm_parallel)"
        )

    async def evaluate_query(
        self,
        query_text: str,
        site_config: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluate if elicitation is needed for a query.

        Args:
            query_text: User's query text
            site_config: Site configuration dict (from get_config_for_site)

        Returns:
            Elicitation prompt dict with "text" and "questions" if information is missing, None otherwise
        """
        intent_elicitations = site_config.get("intent_elicitations", [])

        if not intent_elicitations:
            logger.debug("No intent_elicitations in site config")
            return None

        logger.debug(
            f"Evaluating query with {len(intent_elicitations)} intent-elicitation pairs"
        )

        # Step 1: Detect matching intents and get their required_info
        matching_required_info = await self.intent_detector.detect_intents(
            query=query_text, intent_elicitations=intent_elicitations
        )

        if not matching_required_info:
            logger.info("No matching intents - no elicitation needed")
            return None

        # Step 2: Evaluate required_info checks
        elicitation_prompt = await self.elicitation_checker.evaluate_elicitation(
            query=query_text, required_info_configs=matching_required_info
        )

        if elicitation_prompt:
            logger.info(f"Elicitation needed: {elicitation_prompt}")
        else:
            logger.info("All checks satisfied - no elicitation needed")

        return elicitation_prompt
