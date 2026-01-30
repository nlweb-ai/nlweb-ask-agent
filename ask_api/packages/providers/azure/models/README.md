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

scoring-llm-model:
  llm_type: azure_openai
  model: gpt-4.1-mini
  endpoint_env: AZURE_OPENAI_ENDPOINT
  api_key_env: AZURE_OPENAI_KEY
  api_version: "2024-02-01"
  auth_method: api_key
  import_path: nlweb_azure_models.llm.azure_oai
  class_name: AzureOpenAIScoringProvider
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

### LLM Provider (Generative)
- GPT-4, GPT-3.5-turbo, and other Azure OpenAI models
- Structured output with JSON schema
- Managed identity (Azure AD) authentication
- API key authentication
- Configurable API versions

### Scoring Provider (Ranking/Relevance)
- LLM-based scoring for search result ranking
- Scores items on relevance to user queries (0-100 scale)
- Supports item ranking, intent detection, and presence checking
- Same authentication methods as generative LLMs
- Optimized prompts for consistent scoring
- Batch processing support for efficient ranking

### Embedding Provider
- text-embedding-ada-002 and newer models
- Managed identity (Azure AD) authentication
- API key authentication
- Batch processing support

## Scoring Provider Configuration

The Azure OpenAI scoring provider uses LLMs to score search results for relevance. This is an alternative to specialized scoring models like Pi Labs.

### Scoring Configuration Options

**Option 1: Azure OpenAI (LLM-based scoring)**
```yaml
scoring-llm-model:
  llm_type: azure_openai
  model: gpt-4.1-mini  # Use mini models for cost efficiency
  endpoint_env: AZURE_OPENAI_ENDPOINT
  api_key_env: AZURE_OPENAI_KEY
  api_version: "2024-02-01"
  auth_method: api_key  # or azure_ad
  import_path: nlweb_azure_models.llm.azure_oai
  class_name: AzureOpenAIScoringProvider

ranking_config:
  scoring_questions:
    - "Is this item relevant to the query?"
```

**Option 2: Pi Labs (Specialized scoring model)**
```yaml
scoring-llm-model:
  llm_type: pilabs
  import_path: nlweb_pilabs_models.llm.pi_labs
  class_name: PiLabsScoringProvider
  endpoint_env: PI_LABS_ENDPOINT
  api_key_env: PI_LABS_KEY

ranking_config:
  scoring_questions:
    - "Is this item relevant to the query?"
```

### Scoring Use Cases

1. **Item Ranking**: Score search results based on relevance to user queries
   - Input: User query + item description
   - Output: Relevance score (0-100) + description
   - Uses NLWeb ranking prompt template

2. **Intent Detection**: Determine if a query matches a specific intent
   - Input: User query + intent to check
   - Output: Match score (0-100)

3. **Presence Checking**: Check if required information is present in a query
   - Input: User query + required information
   - Output: Presence score (0-100)

### Prompt Template Approach

Azure OpenAI scoring uses **direct prompt templates** (not question-based scoring):
- Item ranking uses the NLWeb ranking prompt template
- Focuses on relevance judgment and explanation generation
- The `scoring_questions` config field is ignored (used only by PI Labs)
- Leverages LLM's reasoning capabilities for nuanced scoring

### When to Use Each Scoring Provider

**Azure OpenAI Scoring:**
- ✅ Flexible - works with any domain/content type
- ✅ Leverages latest LLM reasoning capabilities
- ✅ No separate model deployment needed
- ⚠️ Higher latency (50-200ms per item)
- ⚠️ Higher cost per scoring operation

**Pi Labs Scoring:**
- ✅ Optimized for scoring performance
- ✅ Lower latency (~10-50ms per item)
- ✅ Lower cost per operation
- ⚠️ Requires separate Pi Labs deployment
- ⚠️ Domain-specific tuning may be needed

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

scoring-llm-model:
  llm_type: azure_openai
  model: gpt-4.1-mini
  endpoint_env: AZURE_OPENAI_ENDPOINT
  api_key_env: AZURE_OPENAI_KEY
  api_version: "2024-02-01"
  auth_method: azure_ad
  import_path: nlweb_azure_models.llm.azure_oai
  class_name: AzureOpenAIScoringProvider

ranking_config:
  scoring_questions:
    - "Is this item relevant to the query?"
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
