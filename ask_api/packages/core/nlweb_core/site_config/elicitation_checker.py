"""
Elicitation checking - verifies if required information is present in query using LLM scoring.
"""

import logging
from typing import List, Dict, Any, Optional
from nlweb_core.config import get_config
from nlweb_core.llm import ask_llm_parallel
from nlweb_core.llm_models import QuestionResponse
from nlweb_core.scoring import ScoringContext

logger = logging.getLogger(__name__)


class ElicitationChecker:
    """
    Checks if required information is present in queries using score-based detection.
    Uses scoring LLM: score >= 70 = present.
    """

    # Score threshold for presence detection (0-100 scale - Pi Labs provider multiplies by 100)
    PRESENCE_THRESHOLD = 70

    def __init__(self):
        """
        Initialize ElicitationChecker.
        Uses scoring LLM model from CONFIG via ask_llm_parallel.
        """
        logger.info("ElicitationChecker initialized (uses scoring LLM model)")

    def _get_default_check_prompt(self, required_info: str) -> str:
        """
        Generate default check detection prompt from value.

        Args:
            required_info: Required info value (e.g., "location", "cuisine")

        Returns:
            Default detection prompt
        """
        readable_value = required_info.replace("_", " ")
        return f"Does the query contain the required information: {readable_value}?"

    def _get_default_elicitation_prompt(self, required_info: str) -> str:
        """
        Generate default elicitation prompt from value.

        Args:
            required_info: Required info value (e.g., "location", "cuisine")

        Returns:
            Default elicitation prompt to ask user
        """
        readable_value = required_info.replace("_", " ")
        # Generate more natural questions based on common patterns
        if required_info == "location":
            return "Where are you located?"
        elif required_info in ["cuisine", "cuisine_type"]:
            return "What type of cuisine are you interested in?"
        elif required_info in ["dish", "dish_type"]:
            return "What specific dish would you like?"
        elif "time" in required_info:
            return f"What is your preferred {readable_value}?"
        else:
            return f"What is your {readable_value}?"

    async def evaluate_elicitation(
        self, query: str, required_info_configs: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluate required_info checks from matching intents using batch scoring.

        Works with flattened structure - input is list of required_info objects directly.

        Args:
            query: User's query text
            required_info_configs: List of required_info objects from matching intents
                Format: [{"value": "location", "detection_prompt": "..."}, ...]

        Returns:
            Dict with "text" and "questions" array (v0.54 format), or None if all checks satisfied
            Format: {"text": "intro text", "questions": [{"id": "q1", "text": "...", "type": "text"}]}
        """
        if not required_info_configs:
            logger.debug("No required_info to evaluate")
            return None

        logger.debug(
            f"Evaluating required_info for query: '{query}' "
            f"({len(required_info_configs)} required_info items)"
        )

        # Deduplicate by required_info value
        # Use dict to keep track: {value: info_object}
        all_required_info: Dict[str, Dict[str, Any]] = {}

        for info in required_info_configs:
            required_info_value = info.get("value")
            if required_info_value:
                # If we've seen this required_info before, keep the one with more detail
                # (e.g., prefer custom detection_prompt over defaults)
                if required_info_value not in all_required_info:
                    all_required_info[required_info_value] = info
                else:
                    # Keep the info with custom prompts if available
                    existing = all_required_info[required_info_value]
                    if (
                        "detection_prompt" in info
                        and "detection_prompt" not in existing
                    ):
                        all_required_info[required_info_value] = info

        logger.debug(
            f"Total unique required_info to evaluate: {len(all_required_info)}"
        )

        if not all_required_info:
            return None

        # Batch check all unique required_info using scoring provider
        contexts = []  # ScoringContext objects for scoring provider
        required_info_list = list(all_required_info.items())

        for required_info, info in required_info_list:
            # Build ScoringContext for scoring provider
            contexts.append(ScoringContext(query=query, required_info=required_info))

        # Call scoring provider in batch with standard question
        scoring_question = "Does the query contain the required information?"
        try:
            provider = get_config().get_scoring_provider("default")
            results = await provider.score_batch(
                [scoring_question],
                contexts,
                timeout=8,
            )

            # Determine which required_info are missing
            missing_info = []
            for i, (required_info, info) in enumerate(required_info_list):
                result = results[i] if i < len(results) else None
                # Handle exceptions or missing results - treat as missing info
                if result is None or isinstance(result, BaseException):
                    logger.warning(
                        f"Required info '{required_info}' scoring failed: {result}"
                    )
                    missing_info.append(info)
                    continue
                score = result  # score is now a float directly

                if score >= self.PRESENCE_THRESHOLD:
                    logger.debug(
                        f"Required info '{required_info}': PRESENT "
                        f"(score: {score} >= {self.PRESENCE_THRESHOLD})"
                    )
                else:
                    logger.debug(
                        f"Required info '{required_info}': MISSING "
                        f"(score: {score} < {self.PRESENCE_THRESHOLD})"
                    )
                    missing_info.append(info)

            # Generate follow-up prompt for missing required_info
            if missing_info:
                logger.info(
                    f"Elicitation needed: {len(missing_info)} required_info missing "
                    f"({[i.get('value') for i in missing_info]})"
                )
                return await self._generate_follow_up(query, missing_info)

            logger.info("All elicitation required_info satisfied - no follow-up needed")
            return None

        except Exception as e:
            logger.error(
                f"Error during batch elicitation evaluation: {e}", exc_info=True
            )
            # On error, don't block the query - skip elicitation
            raise

    async def _generate_follow_up(
        self, query: str, missing_info: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate structured elicitation response for missing required_info using LLM.

        Args:
            query: User's original query
            missing_info: List of required_info dicts that are missing

        Returns:
            Dict with "text" and "questions" in v0.54 format
            Format: {"text": "intro text", "questions": [{"id": "q1", "text": "...", "type": "text"}]}
        """
        # Collect missing required_info values (filter out None values)
        missing_values: List[str] = [
            v
            for info in missing_info
            if (v := info.get("value")) is not None and isinstance(v, str)
        ]

        # Generate questions array - one question per missing info
        questions = []
        for info in missing_info:
            required_info_value = info.get("value", "unknown")

            # Use required_info value as ID (e.g., "location", "dietary_restrictions")
            question_id = required_info_value

            # Always use default elicitation prompt (config doesn't specify elicitation_prompt)
            question_text = self._get_default_elicitation_prompt(required_info_value)

            # Always use "text" type (config doesn't specify type or options)
            question = {"id": question_id, "text": question_text, "type": "text"}

            questions.append(question)

        # Try to generate contextual composite question using LLM
        composite_text = None
        try:
            llm_prompt = self._build_llm_composite_prompt(query, missing_values)

            results = await ask_llm_parallel(
                prompts=[llm_prompt],
                schema=QuestionResponse,
                level="low",  # Use low-tier LLM for cost efficiency
                timeout=5,
                max_length=200,
            )

            if results and len(results) > 0:
                result = results[0]
                # Check for exceptions or validation errors
                if not isinstance(result, Exception):
                    composite_text = result.question.strip()
                    if composite_text:
                        logger.debug(
                            f"LLM-generated composite question: {composite_text}"
                        )

        except Exception as e:
            logger.warning(f"Failed to generate LLM composite question: {e}")
            raise

        # Fallback composite text if LLM didn't generate one
        if not composite_text:
            readable_values = [v.replace("_", " ") for v in missing_values]
            if len(missing_values) == 1:
                composite_text = f'To help with your query about "{query}", could you tell me your {readable_values[0]}?'
            else:
                values_str = (
                    ", ".join(readable_values[:-1]) + f" and {readable_values[-1]}"
                )
                composite_text = f'To provide the best results for "{query}", I need to know your {values_str}.'

        # Return v0.54 compliant elicitation structure
        return {"text": composite_text, "questions": questions}

    def _build_llm_composite_prompt(self, query: str, missing_values: List[str]) -> str:
        """
        Build prompt for LLM to generate a self-contained composite question for elicitation.

        This generates the outer "text" field - a complete question that summarizes the whole
        situation and asks about ALL missing required_info together.

        Args:
            query: User's original query
            missing_values: List of missing required_info values

        Returns:
            Prompt for LLM
        """
        missing_str = ", ".join(missing_values)

        return f"""The user asked: "{query}"

The query is missing the following required information: {missing_str}

Generate a natural, friendly, self-contained question that asks the user for ALL the missing information. The question should:
- Be conversational and helpful
- Reference the user's original query for context
- Ask for ALL the specific missing information in one cohesive question
- Be clear and actionable (1-2 sentences)

Examples:
User query: "dessert recipes"
Missing: cuisine, dish
Good question: "To help you find the perfect dessert recipe, what type of cuisine or specific dish are you interested in?"

User query: "best restaurants"
Missing: location
Good question: "I'd be happy to help you find great restaurants! Where are you located?"

User query: "dinner ideas"
Missing: dietary_restrictions, cooking_time
Good question: "To provide the best dinner recommendations, could you tell me about any dietary restrictions and how much time you have for cooking?"

User query: "pasta"
Missing: location, cuisine
Good question: "To help you find great pasta options, where are you located and what type of cuisine are you looking for?"

Now generate the question:"""
