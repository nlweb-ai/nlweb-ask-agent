# nlweb-azure-vectordb

Azure AI Search provider for NLWeb.

## Overview

This is a **blueprint package** demonstrating how to create individual provider packages for NLWeb. It contains only the Azure AI Search retrieval provider.

Third-party developers can use this as a template for creating their own provider packages (e.g., `nlweb-pinecone`, `nlweb-weaviate`, etc.).

## Installation

```bash
pip install nlweb-core nlweb-azure-vectordb
```

For LLM and embedding, you'll also need a model provider:
```bash
pip install nlweb-azure-models
```

Or use the bundle packages:
```bash
pip install nlweb-core nlweb-retrieval nlweb-models
```

## Configuration

Create `config.yaml`:

```yaml
retrieval:
  provider: azure_ai_search
  import_path: nlweb_azure_vectordb.azure_search_client
  class_name: AzureSearchClient
  api_endpoint_env: AZURE_SEARCH_ENDPOINT
  auth_method: azure_ad  # or api_key
  index_name: my-search-index
```

### Authentication Methods

#### API Key Authentication
```yaml
retrieval:
  provider: azure_ai_search
  import_path: nlweb_azure_vectordb.azure_search_client
  class_name: AzureSearchClient
  api_endpoint_env: AZURE_SEARCH_ENDPOINT
  api_key_env: AZURE_SEARCH_KEY
  auth_method: api_key
  index_name: my-index
```

Set environment variables:
```bash
export AZURE_SEARCH_ENDPOINT=https://your-service.search.windows.net
export AZURE_SEARCH_KEY=your_key_here
```

#### Managed Identity (Azure AD) Authentication
```yaml
retrieval:
  provider: azure_ai_search
  import_path: nlweb_azure_vectordb.azure_search_client
  class_name: AzureSearchClient
  api_endpoint_env: AZURE_SEARCH_ENDPOINT
  auth_method: azure_ad
  index_name: my-index
```

Set environment variable:
```bash
export AZURE_SEARCH_ENDPOINT=https://your-service.search.windows.net
```

## Usage

```python
import nlweb_core

# Initialize
nlweb_core.init(config_path="./config.yaml")

# Search
from nlweb_core import retriever

results = await retriever.search(
    query="example query",
    site="example.com",
    num_results=10
)
```

## Features

- Vector similarity search with Azure AI Search
- Hybrid search (vector + keyword)
- Managed identity (Azure AD) authentication support
- API key authentication support
- Configurable index names
- Compatible with NLWeb Protocol v0.5

## Creating Your Own Provider Package

Use this package as a template:

1. **Create package structure**:
   ```
   nlweb-yourprovider/
   ├── pyproject.toml
   ├── README.md
   └── nlweb_yourprovider/
       ├── __init__.py
       └── your_client.py
   ```

2. **Implement VectorDBClientInterface**:
   ```python
   from nlweb_core.retriever import VectorDBClientInterface

   class YourClient(VectorDBClientInterface):
       async def search(self, query, site, num_results, **kwargs):
           # Your implementation
           pass
   ```

3. **Declare dependencies** in `pyproject.toml`:
   ```toml
   dependencies = [
       "nlweb-core>=0.5.0",
       "your-provider-sdk>=1.0.0",
   ]
   ```

4. **Publish to PyPI**:
   ```bash
   python -m build
   twine upload dist/*
   ```

## License

MIT License - Copyright (c) 2025 Microsoft Corporation
