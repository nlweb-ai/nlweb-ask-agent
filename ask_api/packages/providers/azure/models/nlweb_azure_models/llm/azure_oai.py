# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.

Code for calling Azure Open AI endpoints for LLM functionality.
"""

import logging
import json
from openai import AsyncAzureOpenAI
import asyncio
from typing import Dict, Any
from nlweb_core.llm import GenerativeLLMProvider
from nlweb_core.scoring import ScoringLLMProvider, ScoringContext
from nlweb_core.azure_credentials import get_openai_token_provider

logger = logging.getLogger(__name__)


def normalize_schema_for_structured_output(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a schema to be compatible with Azure OpenAI Structured Outputs.

    Handles two input formats:
    1. Proper JSON Schema (has "type": "object" and "properties")
    2. Informal dict schemas (e.g., {"field": "description"})

    Azure OpenAI Structured Outputs requirements:
    - Root must be "type": "object"
    - All fields must be in "required" array
    - Must include "additionalProperties": false

    Args:
        schema: Input schema (either proper JSON Schema or informal dict)

    Returns:
        Normalized JSON Schema compatible with Structured Outputs
    """
    # Check if this is already a proper JSON Schema
    if schema.get("type") == "object" and "properties" in schema:
        # Already proper JSON Schema - ensure it has required fields for structured outputs
        normalized = schema.copy()

        # Ensure additionalProperties is false (required for strict mode)
        normalized["additionalProperties"] = False

        # Ensure all properties are in required array
        if "properties" in normalized:
            normalized["required"] = list(normalized["properties"].keys())

        return normalized

    # Handle Pydantic-generated schemas (have $defs, title, etc.)
    if "$defs" in schema or "title" in schema:
        # This is a Pydantic model_json_schema() output
        normalized = schema.copy()
        normalized["additionalProperties"] = False
        if "properties" in normalized and "required" not in normalized:
            normalized["required"] = list(normalized["properties"].keys())
        return normalized

    # Convert informal schema to proper JSON Schema
    # Informal format: {"field_name": "description of field"}
    properties = {}
    for key, value in schema.items():
        if isinstance(value, str):
            # Infer type from description keywords
            description = value.lower()
            if "integer" in description or "score" in description:
                properties[key] = {"type": "integer", "description": value}
            elif "number" in description or "float" in description:
                properties[key] = {"type": "number", "description": value}
            elif "boolean" in description or "true/false" in description:
                properties[key] = {"type": "boolean", "description": value}
            elif "array" in description or "list" in description:
                properties[key] = {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": value,
                }
            else:
                # Default to string
                properties[key] = {"type": "string", "description": value}
        elif isinstance(value, dict):
            # Already a property definition
            properties[key] = value
        else:
            # Fallback to string
            properties[key] = {"type": "string"}

    return {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys()),
        "additionalProperties": False,
    }


class AzureOpenAIProvider(GenerativeLLMProvider):
    """Implementation of GenerativeLLMProvider for Azure OpenAI."""

    # Global client with thread-safe initialization
    _client_lock = asyncio.Lock()
    _client = None

    @classmethod
    async def get_client(
        cls,
        endpoint: str | None = None,
        api_key: str | None = None,
        api_version: str | None = None,
        auth_method: str = "api_key",
        **kwargs,
    ) -> AsyncAzureOpenAI | None:
        """
        Get or initialize the Azure OpenAI client.

        Args:
            endpoint: Azure OpenAI endpoint URL (required)
            api_key: API key (required)
            api_version: API version (required)
            auth_method: Authentication method (required)

        Returns:
            Configured AsyncAzureOpenAI client
        """
        if not endpoint or not api_version:
            error_msg = f"Missing required Azure OpenAI configuration - endpoint: {endpoint}, api_version: {api_version}"
            raise ValueError(error_msg)

        # Create client with the resolved endpoint/api_version
        async with cls._client_lock:  # Thread-safe client initialization
            # Always create a new client if we don't have one, or if the endpoint changed
            if (
                cls._client is None
                or not hasattr(cls, "_last_endpoint")
                or cls._last_endpoint != endpoint
            ):
                # Create new client
                try:
                    if auth_method == "azure_ad":
                        token_provider = await get_openai_token_provider()

                        cls._client = AsyncAzureOpenAI(
                            azure_endpoint=endpoint,
                            azure_ad_token_provider=token_provider,
                            api_version=api_version,
                            timeout=30.0,
                        )
                    elif auth_method == "api_key":
                        if not api_key:
                            error_msg = "Missing required Azure OpenAI API key for api_key authentication"
                            raise ValueError(error_msg)

                        cls._client = AsyncAzureOpenAI(
                            azure_endpoint=endpoint,
                            api_key=api_key,
                            api_version=api_version,
                            timeout=30.0,  # Set timeout explicitly
                        )
                    else:
                        error_msg = f"Unsupported authentication method: {auth_method}"
                        raise ValueError(error_msg)

                    # Track the endpoint we used to create this client
                    cls._last_endpoint = endpoint

                except Exception as e:
                    raise

        return cls._client

    @classmethod
    def clean_response(cls, content: str | None) -> Dict[str, Any]:
        """
        Clean and extract JSON content from OpenAI response.

        Args:
            content: The content to clean. May be None.

        Returns:
            Parsed JSON object or empty dict if content is None or invalid

        Raises:
            ValueError: If the content doesn't contain a valid JSON object
        """
        # Handle None content case
        if content is None:
            return {}

        # Handle empty string case
        response_text = content.strip()
        if not response_text:
            return {}

        # Remove markdown code block indicators if present
        response_text = response_text.replace("```json", "").replace("```", "").strip()

        # Find the JSON object within the response
        start_idx = response_text.find("{")
        end_idx = response_text.rfind("}") + 1

        if start_idx == -1 or end_idx == 0:
            error_msg = "No valid JSON object found in response"
            return {}

        json_str = response_text[start_idx:end_idx]

        try:
            result = json.loads(json_str)
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse response as JSON: {e}")
            raise e

    async def get_completion(
        self,
        prompt: str,
        schema: Dict[str, Any],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: float = 8.0,
        endpoint: str | None = None,
        api_key: str | None = None,
        api_version: str | None = None,
        auth_method: str = "api_key",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Get completion from Azure OpenAI.

        Args:
            prompt: The prompt to send to the model
            schema: JSON schema for the expected response
            model: Specific model to use (required)
            endpoint: Azure OpenAI endpoint URL (required)
            api_key: API key (required)
            api_version: API version (required)
            temperature: Model temperature
            max_tokens: Maximum tokens in the generated response
            timeout: Request timeout in seconds
            auth_method: Authentication method ('api_key' or 'azure_ad')
            **kwargs: Additional provider-specific arguments

        Returns:
            Parsed JSON response

        Raises:
            ValueError: If the response cannot be parsed as valid JSON
            TimeoutError: If the request times out
        """
        # Get client with all required parameters
        client = await self.get_client(
            endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
            auth_method=auth_method,
        )
        if client is None:
            return {}
        if model is None:
            return {}

        # Normalize schema for structured outputs
        normalized_schema = normalize_schema_for_structured_output(schema)

        # System prompt - can be simpler now since schema is enforced by API
        system_prompt = "You are a helpful assistant. Respond with JSON matching the required schema."

        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
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
                    model=model,
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


# Create a singleton instance
provider = AzureOpenAIProvider()

# For backwards compatibility
get_azure_openai_completion = provider.get_completion


class AzureOpenAIScoringProvider(ScoringLLMProvider):
    """Implementation of ScoringLLMProvider for Azure OpenAI.

    This provider uses Azure OpenAI to score items based on relevance to a query.
    It returns numeric scores between 0-100.
    """

    # Global client with thread-safe initialization
    _client_lock = asyncio.Lock()
    _client = None
    _last_endpoint = None

    def __init__(self, endpoint: str, api_key: str | None = None, **kwargs):
        """Initialize the Azure OpenAI scoring provider.

        Args:
            endpoint: Azure OpenAI endpoint URL (required)
            api_key: API key for authentication (required for api_key auth, optional for azure_ad)
            **kwargs: Additional configuration (api_version, auth_method, model)
        """
        self.endpoint = endpoint
        self.api_key = api_key
        self.api_version = kwargs.get("api_version", "2024-02-01")
        self.auth_method = kwargs.get("auth_method", "api_key")
        self.model = kwargs.get("model", "gpt-4.1-mini")

    @classmethod
    async def get_client(
        cls,
        endpoint: str | None = None,
        api_key: str | None = None,
        api_version: str | None = None,
        auth_method: str = "api_key",
        **kwargs,
    ) -> AsyncAzureOpenAI | None:
        """Get or initialize the Azure OpenAI client.

        Args:
            endpoint: Azure OpenAI endpoint URL (required)
            api_key: API key (required for api_key auth)
            api_version: API version (required)
            auth_method: Authentication method ('api_key' or 'azure_ad')

        Returns:
            Configured AsyncAzureOpenAI client or None on error
        """
        if not endpoint or not api_version:
            error_msg = f"Missing required Azure OpenAI configuration - endpoint: {endpoint}, api_version: {api_version}"
            raise ValueError(error_msg)

        # Create client with the resolved endpoint/api_version
        async with cls._client_lock:  # Thread-safe client initialization
            # Always create a new client if we don't have one, or if the endpoint changed
            if cls._client is None or cls._last_endpoint != endpoint:
                try:
                    if auth_method == "azure_ad":
                        token_provider = await get_openai_token_provider()

                        cls._client = AsyncAzureOpenAI(
                            azure_endpoint=endpoint,
                            azure_ad_token_provider=token_provider,
                            api_version=api_version,
                            timeout=30.0,
                        )
                    elif auth_method == "api_key":
                        if not api_key:
                            error_msg = "Missing required Azure OpenAI API key for api_key authentication"
                            raise ValueError(error_msg)

                        cls._client = AsyncAzureOpenAI(
                            azure_endpoint=endpoint,
                            api_key=api_key,
                            api_version=api_version,
                            timeout=30.0,
                        )
                    else:
                        error_msg = f"Unsupported authentication method: {auth_method}"
                        raise ValueError(error_msg)

                    # Track the endpoint we used to create this client
                    cls._last_endpoint = endpoint

                except Exception as e:
                    raise ValueError(f"Failed to initialize Azure OpenAI client: {e}")

        return cls._client

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
            prompt = f"""Assign a score between 0 and 100 to the following {item_type} based on how relevant it is to the user's question. Use your knowledge from other sources, about the item, to make a judgement.

If the score is above 50, provide a short description of the item highlighting the relevance to the user's question, without mentioning the user's question.

Provide an explanation of the relevance of the item to the user's question, without mentioning the user's question or the score or explicitly mentioning the term relevance.

If the score is below 75, in the description, include the reason why it is still relevant.

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
        # Use instance config as defaults, allow kwargs to override
        endpoint = kwargs.get("endpoint", self.endpoint)
        api_key = kwargs.get("api_key", self.api_key)
        api_version = kwargs.get("api_version", self.api_version)
        auth_method = kwargs.get("auth_method", self.auth_method)
        model = kwargs.get("model", self.model)

        if not model:
            raise ValueError("Model name is required for Azure OpenAI scoring")

        # Get client
        client = await self.get_client(
            endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
            auth_method=auth_method,
        )
        if client is None:
            raise ValueError("Failed to initialize Azure OpenAI client")

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
                client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=500,
                    temperature=0.3,  # Lower temperature for more consistent scoring
                    top_p=0.1,
                    stream=False,
                    model=model,
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


# Note: Scoring provider instances are created and cached by get_scoring_provider() in nlweb_core.scoring
# No module-level singleton needed here
