# nlweb-cosmos-object-db

Azure Cosmos DB object lookup provider for NLWeb.

## Overview

This provider enables NLWeb to enrich vector search results with full documents from Azure Cosmos DB. When vector databases return truncated content, this provider fetches the complete documents from Cosmos DB using document IDs.

## Installation

```bash
pip install nlweb-core nlweb-cosmos-object-db
```

For a complete setup with vector search:
```bash
pip install nlweb-core nlweb-azure-vectordb nlweb-cosmos-object-db
```

## Configuration

Create `config.yaml`:

```yaml
object_storage:
  type: cosmos
  enabled: true
  endpoint_env: AZURE_COSMOS_ENDPOINT
  database_name: your-database
  container_name: your-container
  partition_key: /"@id"
  import_path: nlweb_cosmos_object_db.cosmos_lookup
  class_name: CosmosObjectLookup
```

### Authentication

This provider uses **Azure AD Managed Identity** authentication via `DefaultAzureCredential`. No API keys required.

Set environment variable:
```bash
export AZURE_COSMOS_ENDPOINT=https://your-account.documents.azure.com:443/
```

### Azure AD Setup

Ensure your Azure identity has appropriate Cosmos DB permissions:
- `Cosmos DB Built-in Data Reader` role
- Or custom role with `Microsoft.DocumentDB/databaseAccounts/readMetadata` and read permissions

## Usage

The provider automatically enriches search results when configured:

```python
import nlweb_core

# Initialize with config
nlweb_core.init(config_path="./config.yaml")

from nlweb_core import retriever

# Search with automatic enrichment
results = await retriever.search(
    query="example query",
    site="example.com",
    num_results=10,
    enrich_from_storage=True  # Enable Cosmos DB enrichment
)

# Results now contain full documents from Cosmos DB
for result in results:
    print(result.content)  # Full content instead of truncated text
```

## How It Works

1. **Vector Search**: NLWeb queries the vector database (e.g., Azure AI Search) and gets IDs + truncated content
2. **ID Extraction**: Document IDs are extracted from vector search results
3. **Cosmos DB Lookup**: Provider queries Cosmos DB by `@id` field to fetch full documents
4. **Content Enrichment**: Full documents replace truncated content in search results
5. **Ranking**: LLM ranks the enriched results

## Features

- Azure AD managed identity authentication (no API keys)
- Async-compatible using thread executors
- Parameterized queries to prevent injection
- Configurable database, container, and partition key
- Seamless integration with NLWeb retrieval pipeline
- Compatible with NLWeb Protocol v0.5+

## Document Structure

Your Cosmos DB documents should have an `@id` field that matches the IDs returned by your vector database:

```json
{
  "@id": "doc-12345",
  "content": "Full document content here...",
  "metadata": {
    "title": "Document Title",
    "url": "https://example.com/page"
  }
}
```

## Configuration Options

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | Must be "cosmos" |
| `enabled` | Yes | Set to `true` to enable enrichment |
| `endpoint_env` | Yes | Environment variable name for Cosmos endpoint |
| `database_name` | Yes | Cosmos DB database name |
| `container_name` | Yes | Cosmos DB container name |
| `partition_key` | Yes | Partition key path (e.g., `/"@id"`) |
| `import_path` | Yes | `nlweb_cosmos_object_db.cosmos_lookup` |
| `class_name` | Yes | `CosmosObjectLookup` |

## Creating Your Own Object Lookup Provider

Use this package as a template:

1. **Create package structure**:
   ```
   nlweb-your-objectdb/
   ├── pyproject.toml
   ├── README.md
   └── nlweb_your_objectdb/
       ├── __init__.py
       └── your_lookup.py
   ```

2. **Implement ObjectLookupInterface**:
   ```python
   from nlweb_core.retriever import ObjectLookupInterface

   class YourLookup(ObjectLookupInterface):
       async def get_by_id(self, doc_id: str) -> dict:
           # Your implementation
           pass
   ```

3. **Declare dependencies** in `pyproject.toml`:
   ```toml
   dependencies = [
       "nlweb-core>=0.5.5",
       "your-database-sdk>=1.0.0",
   ]
   ```

4. **Configure in NLWeb**:
   ```yaml
   object_storage:
     import_path: nlweb_your_objectdb.your_lookup
     class_name: YourLookup
   ```

## License

MIT License - Copyright (c) 2025 Microsoft Corporation
