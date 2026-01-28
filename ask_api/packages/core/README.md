# nlweb-core

Core framework for NLWeb - Natural Language Web interface with config-driven provider architecture.

## Overview

`nlweb-core` provides the foundational framework for building natural language interfaces to web services. It implements:

- Config-driven provider architecture for LLMs, embeddings, and vector databases
- Dynamic module loading based on configuration
- Unified interfaces for retrieval, ranking, and LLM operations
- HTTP server with Server-Sent Events (SSE) streaming support
- NLWeb Protocol v0.5 implementation

## Installation

```bash
pip install nlweb-core
```

**Note**: You also need to install provider packages. See examples below.

## Provider Packages

nlweb-core uses a plugin architecture. Install provider packages separately:

### Bundle Packages (recommended for getting started)
```bash
# All retrieval providers
pip install nlweb-retrieval

# All LLM and embedding providers
pip install nlweb-models
```

### Individual Provider Packages (coming soon)
```bash
# Azure-specific providers
pip install nlweb-azure-vectordb nlweb-azure-models
```

## Quick Start

### 1. Create a configuration file

Create `config.yaml`:

```yaml
# LLM Configuration
llm:
  provider: openai
  import_path: nlweb_models.llm.openai_client
  class_name: OpenAIClient
  api_key_env: OPENAI_API_KEY
  models:
    high: gpt-4
    low: gpt-3.5-turbo

# Embedding Configuration
embedding:
  provider: openai
  import_path: nlweb_models.embedding.openai_embedding
  class_name: get_openai_embeddings
  api_key_env: OPENAI_API_KEY
  model: text-embedding-3-small

# Retrieval Configuration
retrieval:
  provider: elasticsearch
  import_path: nlweb_retrieval.elasticsearch_client
  class_name: ElasticsearchClient
  api_endpoint_env: ELASTICSEARCH_URL
  index_name: my_index
```

### 2. Set environment variables

```bash
export OPENAI_API_KEY=your_key_here
export ELASTICSEARCH_URL=http://localhost:9200
```

### 3. Use in your application

```python
import nlweb_core

# Initialize with your config
nlweb_core.init(config_path="./config.yaml")

# Use the framework
from nlweb_core.simple_server import run_server
run_server()
```

## Configuration

The config file supports three main sections:

### LLM Configuration
- `provider`: Provider name (used for identification)
- `import_path`: Python module path to provider
- `class_name`: Class or function name to import
- `api_key_env`: Environment variable containing API key
- `models`: Model IDs for high/low tiers

### Embedding Configuration
- `provider`: Provider name
- `import_path`: Python module path
- `class_name`: Class or function name
- `model`: Embedding model ID

### Retrieval Configuration
- `provider`: Provider name
- `import_path`: Python module path
- `class_name`: Client class name
- `api_endpoint_env`: Environment variable for endpoint URL
- `index_name`: Index/collection name

## Architecture

nlweb-core provides orchestration layers:
- `retriever.py`: Vector database operations
- `llm.py`: LLM provider dispatch
- `embedding.py`: Embedding generation
- `ranking.py`: LLM-based result ranking
- `simple_server.py`: HTTP server with SSE streaming

All provider-specific code lives in separate packages.

## License

MIT License - Copyright (c) 2025 Microsoft Corporation
