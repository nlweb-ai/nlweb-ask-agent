# NLWeb Package Structure

This document describes the modular package architecture for NLWeb.

## Overview

NLWeb has been refactored from a monolithic structure into 5 pip-installable packages:

1. **nlweb-core** - Framework only (no providers)
2. **nlweb-retrieval** - Bundle of all retrieval providers
3. **nlweb-models** - Bundle of all LLM + embedding providers
4. **nlweb-azure-vectordb** - Blueprint package (Azure AI Search only)
5. **nlweb-azure-models** - Blueprint package (Azure OpenAI only)

## Package Details

### 1. nlweb-core
**Location**: `packages/core/`

**Purpose**: Core framework with provider orchestration, no provider implementations.

**Contains**:
- `config.py` - Configuration management
- `retriever.py` - Retrieval orchestration
- `llm.py` - LLM orchestration
- `embedding.py` - Embedding orchestration
- `ranking.py` - LLM-based ranking
- `simple_server.py` - HTTP server with SSE streaming
- `handler.py` - NLWebHandler class
- `utils.py` - Utility functions
- `query_analysis/` - Query analysis module

**Dependencies**:
- pyyaml>=6.0
- python-dotenv>=1.0.0
- aiohttp>=3.8.0

**Install**:
```bash
pip install nlweb-core
```

### 2. nlweb-retrieval
**Location**: `packages/bundles/retrieval/`

**Purpose**: Bundle containing ALL retrieval providers for backward compatibility.

**Contains**:
- Azure AI Search
- Elasticsearch
- Milvus
- Qdrant
- PostgreSQL (pgvector)
- OpenSearch
- Snowflake Cortex Search
- Shopify MCP
- Cloudflare AutoRAG
- Bing Search

**Dependencies**:
- nlweb-core>=0.5.0
- All provider-specific packages (elasticsearch, qdrant-client, pymilvus, etc.)

**Install**:
```bash
pip install nlweb-retrieval
```

### 3. nlweb-models
**Location**: `packages/bundles/models/`

**Purpose**: Bundle containing ALL LLM and embedding providers.

**Contains**:

*LLM Providers*:
- OpenAI
- Anthropic
- Google Gemini
- Azure OpenAI
- Azure Llama
- Azure DeepSeek
- HuggingFace
- Snowflake
- Ollama
- Inception

*Embedding Providers*:
- OpenAI
- Azure OpenAI
- Google Gemini
- Snowflake
- Ollama
- Elasticsearch

**Dependencies**:
- nlweb-core>=0.5.0
- All provider-specific packages (openai, anthropic, google-cloud-aiplatform, etc.)

**Install**:
```bash
pip install nlweb-models
```

### 4. nlweb-azure-vectordb
**Location**: `packages/providers/azure/vectordb/`

**Purpose**: Blueprint package demonstrating individual provider packaging (Azure AI Search only).

**Contains**:
- Azure AI Search client only

**Dependencies**:
- nlweb-core>=0.5.0
- azure-core
- azure-search-documents>=11.4.0
- azure-identity>=1.12.0

**Install**:
```bash
pip install nlweb-azure-vectordb
```

### 5. nlweb-azure-models
**Location**: `packages/providers/azure/models/`

**Purpose**: Blueprint package for Azure OpenAI (LLM + embedding).

**Contains**:
- Azure OpenAI LLM provider
- Azure OpenAI embedding provider

**Dependencies**:
- nlweb-core>=0.5.0
- openai>=1.12.0
- azure-identity>=1.12.0

**Install**:
```bash
pip install nlweb-azure-models
```

## Installation Patterns

### Pattern 1: Full Bundle (Backward Compatible)
Everything included, works exactly like the old monolithic version:
```bash
pip install nlweb-core nlweb-retrieval nlweb-models
```

### Pattern 2: Azure-Only Stack
Minimal install with only Azure providers:
```bash
pip install nlweb-core nlweb-azure-vectordb nlweb-azure-models
```

### Pattern 3: Mix and Match
Choose specific bundles/providers as needed:
```bash
pip install nlweb-core nlweb-retrieval nlweb-azure-models
```

## Configuration

All packages use a **single config file** approach. No more 6+ config files!

**config.yaml**:
```yaml
llm:
  provider: openai
  import_path: nlweb_models.llm.openai
  class_name: provider
  api_key_env: OPENAI_API_KEY
  models:
    high: gpt-4
    low: gpt-3.5-turbo

embedding:
  provider: openai
  import_path: nlweb_models.embedding.openai_embedding
  class_name: get_openai_embeddings
  api_key_env: OPENAI_API_KEY
  model: text-embedding-3-small

retrieval:
  provider: elasticsearch
  import_path: nlweb_retrieval.elasticsearch_client
  class_name: ElasticsearchClient
  api_endpoint_env: ELASTICSEARCH_URL
  index_name: my_index
```

## Usage

```python
import nlweb_core

# Initialize with config
nlweb_core.init(config_path="./config.yaml")

# Use the framework
from nlweb_core.simple_server import run_server
run_server()
```

## Key Architecture Changes

### Config-Driven Dynamic Imports
**Before**: Hardcoded if/elif chains with 50+ lines per provider type
```python
if db_type == "elasticsearch":
    from nlweb_core.retrieval_providers.elasticsearch_client import ElasticsearchClient
    client_class = ElasticsearchClient
elif db_type == "qdrant":
    # ... 40 more elif blocks
```

**After**: Config-driven dynamic import (5 lines)
```python
import_path = config.import_path  # from config.yaml
class_name = config.class_name
module = __import__(import_path, fromlist=[class_name])
client_class = getattr(module, class_name)
```

### Dependency Management
**Before**: Auto-install packages at runtime (complex, fragile)

**After**: Proper pip dependency declaration in pyproject.toml
```toml
dependencies = [
    "nlweb-core>=0.5.0",
    "elasticsearch[async]>=8,<9",
    "qdrant-client>=1.14.0",
]
```

### Provider Registration
**Before**: Manual registration in core framework

**After**: No registration needed - config specifies import path

## Example Configurations

See `packages/examples/` for complete examples:
- `config_openai_elasticsearch.yaml` - OpenAI + Elasticsearch
- `config_azure_full_stack.yaml` - Full Azure stack
- `config_anthropic_qdrant.yaml` - Anthropic + Qdrant

## Creating Third-Party Provider Packages

Use the Azure blueprint packages as templates:

1. Create package structure
2. Implement required interfaces
3. Declare dependencies in pyproject.toml
4. Publish to PyPI
5. Users add to config.yaml with import_path

See individual package READMEs for detailed instructions.

## Migration from Monolithic Version

1. Install new packages:
   ```bash
   pip install nlweb-core nlweb-retrieval nlweb-models
   ```

2. Create single config.yaml (consolidate old config files)

3. Add `import_path` and `class_name` for each provider

4. Initialize with new API:
   ```python
   import nlweb_core
   nlweb_core.init(config_path="./config.yaml")
   ```

5. Update imports if needed (though most stay the same)

## Benefits

1. **Smaller installs** - Only install what you need
2. **Faster imports** - Don't load unused providers
3. **Better dependency management** - Pip handles everything
4. **Third-party extensibility** - Anyone can create provider packages
5. **Cleaner code** - No hardcoded provider lists
6. **Simpler config** - One file instead of 6+

## License

MIT License - Copyright (c) 2025 Microsoft Corporation
