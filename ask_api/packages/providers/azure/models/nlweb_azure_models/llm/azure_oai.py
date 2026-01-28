# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.

Code for calling Azure Open AI endpoints for LLM functionality.
"""

import json
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncAzureOpenAI
import asyncio
import threading
from typing import Dict, Any
from nlweb_core.llm import GenerativeLLMProvider


class AzureOpenAIProvider(GenerativeLLMProvider):
    """Implementation of GenerativeLLMProvider for Azure OpenAI."""

    # Global client with thread-safe initialization
    _client_lock = threading.Lock()
    _client = None

    @classmethod
    def get_client(cls, endpoint: str | None = None, api_key: str | None = None, api_version: str | None = None, auth_method: str = "api_key", **kwargs) -> AsyncAzureOpenAI | None:
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
        with cls._client_lock:  # Thread-safe client initialization
            # Always create a new client if we don't have one, or if the endpoint changed
            if cls._client is None or not hasattr(cls, '_last_endpoint') or cls._last_endpoint != endpoint:
                # Create new client
                try:
                    if auth_method == "azure_ad":
                        token_provider = get_bearer_token_provider(
                            DefaultAzureCredential(),
                            "https://cognitiveservices.azure.com/.default"
                        )

                        cls._client = AsyncAzureOpenAI(
                            azure_endpoint=endpoint,
                            azure_ad_token_provider=token_provider,
                            api_version=api_version,
                            timeout=30.0
                        )
                    elif auth_method == "api_key":
                        if not api_key:
                            error_msg = "Missing required Azure OpenAI API key for api_key authentication"
                            raise ValueError(error_msg)

                        cls._client = AsyncAzureOpenAI(
                            azure_endpoint=endpoint,
                            api_key=api_key,
                            api_version=api_version,
                            timeout=30.0  # Set timeout explicitly
                        )
                    else:
                        error_msg = f"Unsupported authentication method: {auth_method}"
                        raise ValueError(error_msg)

                    # Track the endpoint we used to create this client
                    cls._last_endpoint = endpoint

                except Exception as e:
                    return None


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
        response_text = response_text.replace('```json', '').replace('```', '').strip()
                
        # Find the JSON object within the response
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}') + 1
        
        if start_idx == -1 or end_idx == 0:
            error_msg = "No valid JSON object found in response"
            return {}
            

        json_str = response_text[start_idx:end_idx]
                
        try:
            result = json.loads(json_str)
            return result
        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse response as JSON: {e}"
            return {}

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
        **kwargs
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
        client = self.get_client(endpoint=endpoint, api_key=api_key, api_version=api_version, auth_method=auth_method)
        if client is None:
            return {}
        if model is None:
            return {}
        system_prompt = f"""Provide a response that matches this JSON schema: {json.dumps(schema)}"""

        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=0.1,
                    stream=False,
                    presence_penalty=0.0,
                    frequency_penalty=0.0,
                    model=model,
                    response_format={"type": "json_object"}
                ),
                timeout=timeout
            )
            
            # Safely extract content from response, handling potential None
            if not response or not hasattr(response, 'choices') or not response.choices:
                return {}
                
            # Check if message and content exist
            if not hasattr(response.choices[0], 'message') or not hasattr(response.choices[0].message, 'content'):
                return {}
                
            ansr_str = response.choices[0].message.content
            ansr = self.clean_response(ansr_str)
            return ansr
            
        except asyncio.TimeoutError:
            return {}
        except Exception as e:
            raise


# Create a singleton instance
provider = AzureOpenAIProvider()

# For backwards compatibility
get_azure_openai_completion = provider.get_completion
