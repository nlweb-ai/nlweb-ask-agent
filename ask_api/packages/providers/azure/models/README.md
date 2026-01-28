# nlweb-azure-models

Azure OpenAI LLM and embedding providers for NLWeb.

## Overview

This is a **blueprint package** demonstrating how to create individual model provider packages for NLWeb. It contains Azure OpenAI implementations for both LLM and embeddings.

Third-party developers can use this as a template for creating their own model provider packages.

## Installation

```bash
pip install nlweb-core nlweb-azure-models
```

For vector search, you'll also need a retrieval provider:
```bash
pip install nlweb-azure-vectordb
```

Or use the bundle packages:
```bash
pip install nlweb-core nlweb-retrieval nlweb-models
```

## Configuration

Create `config.yaml`:

```yaml
llm:
  provider: azure_openai
  import_path: nlweb_azure_models.llm.azure_oai
  class_name: provider
  endpoint_env: AZURE_OPENAI_ENDPOINT
  api_key_env: AZURE_OPENAI_KEY
  api_version: 2024-02-01
  auth_method: azure_ad  # or api_key
  models:
    high: gpt-4
    low: gpt-35-turbo

embedding:
  provider: azure_openai
  import_path: nlweb_azure_models.embedding.azure_oai_embedding
  class_name: get_azure_embedding
  endpoint_env: AZURE_OPENAI_ENDPOINT
  auth_method: azure_ad
  model: text-embedding-ada-002
```

### Authentication Methods

#### API Key Authentication
```yaml
llm:
  provider: azure_openai
  import_path: nlweb_azure_models.llm.azure_oai
  class_name: provider
  endpoint_env: AZURE_OPENAI_ENDPOINT
  api_key_env: AZURE_OPENAI_KEY
  api_version: 2024-02-01
  auth_method: api_key
  models:
    high: gpt-4
    low: gpt-35-turbo
```

Set environment variables:
```bash
export AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
export AZURE_OPENAI_KEY=your_key_here
```

#### Managed Identity (Azure AD) Authentication
```yaml
llm:
  provider: azure_openai
  import_path: nlweb_azure_models.llm.azure_oai
  class_name: provider
  endpoint_env: AZURE_OPENAI_ENDPOINT
  api_version: 2024-02-01
  auth_method: azure_ad
  models:
    high: gpt-4
    low: gpt-35-turbo
```

Set environment variable:
```bash
export AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
```

## Usage

```python
import nlweb_core

# Initialize
nlweb_core.init(config_path="./config.yaml")

# Use LLM
from nlweb_core import llm

result = await llm.ask_llm(
    prompt="Summarize this text",
    schema={"type": "object", "properties": {"summary": {"type": "string"}}},
    level="high"
)

# Use embeddings
from nlweb_core import embedding

vector = await embedding.get_embedding(
    text="Text to embed"
)
```

## Features

### LLM Provider
- GPT-4, GPT-3.5-turbo, and other Azure OpenAI models
- Structured output with JSON schema
- Managed identity (Azure AD) authentication
- API key authentication
- Configurable API versions

### Embedding Provider
- text-embedding-ada-002 and newer models
- Managed identity (Azure AD) authentication
- API key authentication
- Batch processing support

## Complete Azure Stack Example

Use all three Azure packages together:

```bash
pip install nlweb-core nlweb-azure-vectordb nlweb-azure-models
```

```yaml
llm:
  provider: azure_openai
  import_path: nlweb_azure_models.llm.azure_oai
  class_name: provider
  endpoint_env: AZURE_OPENAI_ENDPOINT
  auth_method: azure_ad
  models:
    high: gpt-4
    low: gpt-35-turbo

embedding:
  provider: azure_openai
  import_path: nlweb_azure_models.embedding.azure_oai_embedding
  class_name: get_azure_embedding
  endpoint_env: AZURE_OPENAI_ENDPOINT
  auth_method: azure_ad
  model: text-embedding-ada-002

retrieval:
  provider: azure_ai_search
  import_path: nlweb_azure_vectordb.azure_search_client
  class_name: AzureSearchClient
  api_endpoint_env: AZURE_SEARCH_ENDPOINT
  auth_method: azure_ad
  index_name: my-index
```

## Creating Your Own Model Provider Package

Use this package as a template:

1. **Create package structure**:
   ```
   nlweb-yourprovider/
   ├── pyproject.toml
   ├── README.md
   └── nlweb_yourprovider/
       ├── __init__.py
       ├── llm/
       │   └── your_llm.py
       └── embedding/
           └── your_embedding.py
   ```

2. **Implement provider interface**:
   ```python
   # For LLM
   async def get_completion(prompt, schema, model, timeout, max_tokens):
       # Your implementation
       pass

   # For embedding
   async def get_your_embeddings(text, model):
       # Your implementation
       return [0.1, 0.2, ...]  # List of floats
   ```

3. **Declare dependencies** in `pyproject.toml`
4. **Publish to PyPI**

## License

MIT License - Copyright (c) 2025 Microsoft Corporation
