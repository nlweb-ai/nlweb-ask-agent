# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Azure OpenAI embedding implementation.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

import json
import asyncio
import threading
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from typing import List, Optional
from openai import AsyncAzureOpenAI
from nlweb_core.config import get_config


# Global client with thread-safe initialization
_client_lock = threading.Lock()
azure_openai_client = None

def get_azure_openai_endpoint():
    """Get the Azure OpenAI endpoint from configuration."""
    provider_config = get_config().get_embedding_provider("azure_openai")
    if provider_config and provider_config.endpoint:
        endpoint = provider_config.endpoint
        if endpoint:
            endpoint = endpoint.strip('"')  # Remove quotes if present
            return endpoint
    return None

def get_azure_openai_api_key():
    """Get the Azure OpenAI API key from configuration."""
    provider_config = get_config().get_embedding_provider("azure_openai")
    if provider_config and provider_config.api_key:
        api_key = provider_config.api_key
        if api_key:
            api_key = api_key.strip('"')  # Remove quotes if present
            return api_key
    return None

def get_auth_method():
    """Get the authentication method from configuration."""
    provider_config = get_config().get_embedding_provider("azure_openai")
    if provider_config and provider_config.auth_method:
        return provider_config.auth_method
    # Default to api_key
    return "api_key"

def get_azure_openai_api_version():
    """Get the Azure OpenAI API version from configuration."""
    provider_config = get_config().get_embedding_provider("azure_openai")
    if provider_config and provider_config.api_version:
        api_version = provider_config.api_version
        return api_version
    # Default value if not found in config
    default_version = "2024-10-21"
    return default_version

def get_azure_openai_client():
    """Get or initialize the Azure OpenAI client."""
    global azure_openai_client
    with _client_lock:  # Thread-safe client initialization
        if azure_openai_client is None:
            endpoint = get_azure_openai_endpoint()
            api_version = get_azure_openai_api_version()
            auth_method = get_auth_method()

            if not endpoint or not api_version:
                error_msg = "Missing required Azure OpenAI configuration (endpoint or api_version)"
                raise ValueError(error_msg)

            try:
                if auth_method == "azure_ad":
                    token_provider = get_bearer_token_provider(
                        DefaultAzureCredential(),
                        "https://cognitiveservices.azure.com/.default"
                    )

                    azure_openai_client = AsyncAzureOpenAI(
                        azure_endpoint=endpoint,
                        azure_ad_token_provider=token_provider,
                        api_version=api_version,
                        timeout=30.0
                    )
                elif auth_method == "api_key":
                    api_key = get_azure_openai_api_key()
                    if not api_key:
                        error_msg = "Missing required Azure OpenAI API key for api_key authentication"
                        raise ValueError(error_msg)

                    azure_openai_client = AsyncAzureOpenAI(
                        azure_endpoint=endpoint,
                        api_key=api_key,
                        api_version=api_version,
                        timeout=30.0
                    )
                else:
                    error_msg = f"Unsupported authentication method: {auth_method}"
                    raise ValueError(error_msg)

            except Exception as e:
                raise


    return azure_openai_client

async def get_azure_embedding(
    text: str, 
    model: Optional[str] = None,
    timeout: float = 30.0
) -> List[float]:
    """
    Generate embeddings using Azure OpenAI.
    
    Args:
        text: The text to embed
        model: The model deployment name to use (optional)
        timeout: Maximum time to wait for the embedding response in seconds
        
    Returns:
        List of floats representing the embedding vector
    """
    client = get_azure_openai_client()
    
    # If model is not provided, get from config
    if model is None:
        provider_config = get_config().get_embedding_provider("azure_openai")
        if provider_config and provider_config.model:
            model = provider_config.model
        else:
            # Default to a common embedding model name
            model = "text-embedding-3-small"
    

    if (len(text) > 20000):
        text = text[:20000]

    try:
        response = await client.embeddings.create(
            input=text,
            model=model
        )
        
        embedding = response.data[0].embedding
        return embedding
    except Exception as e:
        raise

async def get_azure_batch_embeddings(
    texts: List[str],
    model: Optional[str] = None,
    timeout: float = 60.0
) -> List[List[float]]:
    """
    Generate embeddings for multiple texts using Azure OpenAI.
    
    Args:
        texts: List of texts to embed
        model: The model deployment name to use (optional)
        timeout: Maximum time to wait for the batch embedding response in seconds
        
    Returns:
        List of embedding vectors, each a list of floats
    """
    client = get_azure_openai_client()
    
    # If model is not provided, get from config
    if model is None:
        provider_config = get_config().get_embedding_provider("azure_openai")
        if provider_config and provider_config.model:
            model = provider_config.model
        else:
            # Default to a common embedding model name
            model = "text-embedding-3-small"
    

    trimmed_texts = []
    for elt in texts:
        if (len(elt) > 12000):
            trimmed_texts.append(elt[:12000])
        else:
            trimmed_texts.append(elt)
    
    try:
        response = await client.embeddings.create(
            input=trimmed_texts,
            model=model
        )
        
        # Extract embeddings in the same order as input texts
        embeddings = [data.embedding for data in response.data]
        return embeddings
    except Exception as e:
        raise