# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.

Code for calling Azure Open AI endpoints for LLM functionality.
"""

import asyncio
import json
import logging
from typing import Any, Dict

from nlweb_core.azure_credentials import get_openai_token_provider
from nlweb_core.llm import GenerativeLLMProvider
from nlweb_core.scoring import ScoringContext, ScoringLLMProvider
from openai import AsyncAzureOpenAI

logger = logging.getLogger(__name__)


def normalize_schema_for_structured_output(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a Pydantic-generated JSON schema for Azure OpenAI Structured Outputs.

    Azure OpenAI Structured Outputs requirements:
    - Root must be "type": "object"
    - All fields must be in "required" array
    - Must include "additionalProperties": false

    Args:
        schema: JSON Schema from Pydantic's model_json_schema()

    Returns:
        Normalized JSON Schema compatible with Structured Outputs
    """
    normalized = schema.copy()

    # Ensure additionalProperties is false (required for strict mode)
    normalized["additionalProperties"] = False

    # Ensure all properties are in required array if not already set
    if "properties" in normalized and "required" not in normalized:
        normalized["required"] = list(normalized["properties"].keys())

    return normalized


class AzureOpenAIProvider(GenerativeLLMProvider):
    """Implementation of GenerativeLLMProvider for Azure OpenAI."""

    def __init__(
        self,
        endpoint: str,
        api_version: str,
        auth_method: str,
        model: str,
        api_key: str | None = None,
    ):
        """Initialize the Azure OpenAI generative provider.

        Args:
            endpoint: Azure OpenAI endpoint URL
            api_version: API version
            auth_method: Authentication method ('api_key' or 'azure_ad')
            model: Model deployment name to use
            api_key: API key for authentication (required if auth_method is 'api_key')

        Raises:
            ValueError: If api_key is missing when auth_method is 'api_key'
        """
        if auth_method == "api_key" and not api_key:
            raise ValueError("api_key is required when auth_method is 'api_key'")

        self.endpoint = endpoint
        self.api_key = api_key
        self.api_version = api_version
        self.auth_method = auth_method
        self.model = model

        # Client initialized lazily on first use
        self._client: AsyncAzureOpenAI | None = None

    async def _ensure_client(self) -> None:
        """Create client if not already initialized."""
        if self._client is not None:
            return

        if self.auth_method == "azure_ad":
            token_provider = await get_openai_token_provider()
            self._client = AsyncAzureOpenAI(
                azure_endpoint=self.endpoint,
                azure_ad_token_provider=token_provider,
                api_version=self.api_version,
                timeout=30.0,
            )
        elif self.auth_method == "api_key":
            self._client = AsyncAzureOpenAI(
                azure_endpoint=self.endpoint,
                api_key=self.api_key,
                api_version=self.api_version,
                timeout=30.0,
            )
        else:
            raise ValueError(f"Unsupported authentication method: {self.auth_method}")

    async def get_completion(
        self,
        prompt: str,
        schema: Dict[str, Any],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: float = 8.0,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Get completion from Azure OpenAI.

        Args:
            prompt: The prompt to send to the model
            schema: JSON schema for the expected response
            temperature: Model temperature
            max_tokens: Maximum tokens in the generated response
            timeout: Request timeout in seconds
            **kwargs: Additional provider-specific arguments (ignored)

        Returns:
            Parsed JSON response

        Raises:
            ValueError: If the response cannot be parsed as valid JSON
            TimeoutError: If the request times out
        """
        await self._ensure_client()
        assert self._client is not None

        # Normalize schema for structured outputs
        normalized_schema = normalize_schema_for_structured_output(schema)

        # System prompt - can be simpler now since schema is enforced by API
        system_prompt = "You are a helpful assistant. Respond with JSON matching the required schema."

        try:
            response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=0.1,
                    stream=False,
                    presence_penalty=0.0,
                    frequency_penalty=0.0,
                    model=self.model,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "response_schema",
                            "strict": True,
                            "schema": normalized_schema,
                        },
                    },
                ),
                timeout=timeout,
            )

            # Safely extract content from response, handling potential None
            if not response or not hasattr(response, "choices") or not response.choices:
                return {}

            # Check if message and content exist
            if not hasattr(response.choices[0], "message") or not hasattr(
                response.choices[0].message, "content"
            ):
                return {}

            # With structured outputs, response is guaranteed to be valid JSON
            content = response.choices[0].message.content
            if content is None:
                return {}

            return json.loads(content)

        except asyncio.TimeoutError:
            raise
        except Exception as e:
            raise

    async def close(self) -> None:
        """Close the Azure OpenAI client and release resources."""
        if self._client is not None:
            await self._client.close()
            self._client = None


class AzureOpenAIScoringProvider(ScoringLLMProvider):
    """Implementation of ScoringLLMProvider for Azure OpenAI.

    This provider uses Azure OpenAI to score items based on relevance to a query.
    It returns numeric scores between 0-100.
    """

    def __init__(
        self,
        endpoint: str,
        api_version: str,
        auth_method: str,
        model: str,
        api_key: str | None = None,
        **kwargs,
    ):
        """Initialize the Azure OpenAI scoring provider.

        Args:
            endpoint: Azure OpenAI endpoint URL
            api_version: API version
            auth_method: Authentication method ('api_key' or 'azure_ad')
            model: Model deployment name to use
            api_key: API key for authentication (required if auth_method is 'api_key')
            **kwargs: Additional configuration (ignored)
        """
        self.endpoint = endpoint
        self.api_key = api_key
        self.api_version = api_version
        self.auth_method = auth_method
        self.model = model

        # Client initialized lazily on first use
        self._client: AsyncAzureOpenAI | None = None

    async def _ensure_client(self) -> None:
        """Create client if not already initialized."""
        if self._client is not None:
            return

        if self.auth_method == "azure_ad":
            token_provider = await get_openai_token_provider()
            self._client = AsyncAzureOpenAI(
                azure_endpoint=self.endpoint,
                azure_ad_token_provider=token_provider,
                api_version=self.api_version,
                timeout=30.0,
            )
        elif self.auth_method == "api_key":
            if not self.api_key:
                raise ValueError(
                    "Missing required Azure OpenAI API key for api_key authentication"
                )
            self._client = AsyncAzureOpenAI(
                azure_endpoint=self.endpoint,
                api_key=self.api_key,
                api_version=self.api_version,
                timeout=30.0,
            )
        else:
            raise ValueError(f"Unsupported authentication method: {self.auth_method}")

    def _build_scoring_prompt(self, context: ScoringContext) -> str:
        """Build a scoring prompt from context.

        Args:
            context: Structured context for scoring

        Returns:
            Formatted prompt string
        """
        # Determine the scoring mode based on context fields
        if context.item_description and context.item_type:
            # Item ranking mode - use the NLWeb ranking prompt template
            item_type = context.item_type or "item"

            # Build base prompt
            prompt = f"""Assign a score between 0 and 100 to the following {item_type} based on how relevant it is to the user's question. Use your knowledge from other sources, about the item, to make a judgement.

If the score is above 50, provide a short description of the item highlighting the relevance to the user's question, without mentioning the user's question.

Provide an explanation of the relevance of the item to the user's question, without mentioning the user's question or the score or explicitly mentioning the term relevance.

If the score is below 75, in the description, include the reason why it is still relevant."""

            # Add freshness context if available
            if context.publication_date and context.age_days is not None:
                prompt += f"""

FRESHNESS CONTEXT:
- Publication date: {context.publication_date}
- Age: {context.age_days} days old

When considering relevance, factor in the item's freshness based on the query intent:
- For queries asking for "latest", "recent", "new", or "today's" content, give higher scores to more recent items
- For queries about specific events, news, or time-sensitive topics, prioritize fresher content
- For evergreen topics (recipes, how-to guides, general information), age is less important
- Very recent items (< 7 days) should get a bonus for time-sensitive queries"""

            prompt += f"""

The user's question is: {context.query}

The item's description is: {context.item_description}"""
        elif context.intent:
            # Intent detection mode
            prompt = f"""Assign a score between 0 and 100 based on how well the user's query matches the specified intent.

User's query: {context.query}

Intent to check: {context.intent}

Provide a score indicating the match strength (0 = no match, 100 = perfect match)."""
        elif context.required_info:
            # Presence checking mode
            prompt = f"""Assign a score between 0 and 100 based on whether the user's query contains the required information.

User's query: {context.query}

Required information: {context.required_info}

Provide a score indicating presence (0 = not present, 100 = fully present)."""
        else:
            # Generic scoring (fallback)
            prompt = f"""Assign a score between 0 and 100 for the following query.

Query: {context.query}

Provide a relevance score."""

        return prompt

    async def score(
        self,
        questions: list[str],
        context: ScoringContext,
        timeout: float = 30.0,
        **kwargs,
    ) -> float:
        """Score a single context.

        Args:
            questions: List of scoring questions (ignored for LLM-based scoring)
            context: Structured context for the scoring operation
            timeout: Request timeout in seconds
            **kwargs: Additional provider-specific arguments (overrides instance config)

        Returns:
            Score between 0-100

        Raises:
            ValueError: If the request fails or response is invalid
            TimeoutError: If the request times out

        Note:
            The 'questions' parameter is ignored for LLM-based scoring to maintain
            interface compatibility. LLM scoring uses a direct prompt template instead.
        """
        await self._ensure_client()
        assert self._client is not None

        # Build prompt (questions parameter is ignored for LLM-based scoring)
        prompt = self._build_scoring_prompt(context)

        # Define the expected JSON schema for structured outputs
        scoring_schema = {
            "type": "object",
            "properties": {
                "score": {
                    "type": "integer",
                    "description": "Relevance score between 0 and 100",
                },
                "description": {
                    "type": "string",
                    "description": "Brief explanation of the score",
                },
            },
            "required": ["score", "description"],
            "additionalProperties": False,
        }
        system_prompt = "You are a scoring assistant. Provide a relevance score and brief explanation."

        try:
            response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=500,
                    temperature=0.3,  # Lower temperature for more consistent scoring
                    top_p=0.1,
                    stream=False,
                    model=self.model,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "scoring_response",
                            "strict": True,
                            "schema": scoring_schema,
                        },
                    },
                ),
                timeout=timeout,
            )

            # Extract and parse response
            if (
                not response
                or not response.choices
                or not response.choices[0].message.content
            ):
                raise ValueError("Empty response from Azure OpenAI")

            content = response.choices[0].message.content

            # With structured outputs, response is guaranteed to be valid JSON
            result = json.loads(content)
            score = result.get("score", 0)

            # Ensure score is in valid range
            if isinstance(score, (int, float)):
                return float(max(0, min(100, score)))
            else:
                raise ValueError(f"Invalid score type: {type(score)}")

        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Azure OpenAI scoring request timed out after {timeout}s"
            )
        except Exception as e:
            raise ValueError(f"Azure OpenAI scoring failed: {e}")

    async def score_batch(
        self,
        questions: list[str],
        contexts: list[ScoringContext],
        timeout: float = 30.0,
        **kwargs,
    ) -> list[float | BaseException]:
        """Score multiple contexts with the given questions in parallel.

        Args:
            questions: List of scoring questions to ask
            contexts: List of contexts to score
            timeout: Request timeout in seconds
            **kwargs: Additional provider-specific arguments

        Returns:
            List of scores (0-100) or Exception for each failed request
        """
        tasks = [
            self.score(questions, context, timeout=timeout, **kwargs)
            for context in contexts
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return list(results)

    async def close(self) -> None:
        """Close the Azure OpenAI client and release resources."""
        if self._client is not None:
            await self._client.close()
            self._client = None
