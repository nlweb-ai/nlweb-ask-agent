# NLWeb Ask Agent - Developer Guide

Quick reference for developing in the nlweb-ask-agent project.

## Project Overview

NLWeb Ask Agent is a distributed question-answering system with semantic search over crawled web content.

**Two Main Services:**
- **Ask API** (`/ask_api`) - REST API for semantic search with MCP/A2A protocol support
- **Crawler** (`/crawler`) - Web crawler for schema.org structured data extraction

## Prerequisites

- [Python 3.12](https://www.python.org/downloads/)
- [uv](https://docs.astral.sh/uv/) - Python package manager
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Azure CLI](https://docs.microsoft.com/cli/azure/install-azure-cli) 2.50+
- [kubectl](https://kubernetes.io/docs/tasks/tools/) (for deployment)

## Quick Start

### 1. Environment Setup

Each service needs credentials from Azure Key Vault:

```bash
# For Ask API
cd ask_api
make init_environment  # Pulls secrets to .env
uv sync               # Install dependencies

# For Crawler
cd crawler
make init_environment  # Pulls secrets to .env
uv sync               # Install dependencies
```

**Important:** You need Azure permissions:
- **Resource Group Access**: Reader role on `rg-nlweb-<env>-<region>`
- **Key Vault Access**: "Key Vault Secrets User" role on the Key Vault

Available environments:
- `nlweb-yoast-centralus` (default in common.mk)
- `nlweb-dev-centralus` (default in crawler)
- `nlweb-westeurope-sweden`

To use a different environment:
```bash
make init_environment ENV_NAME=nlweb-yoast-centralus
```

### 2. Verify Your Credentials

After getting permissions, you may need to refresh your Azure token:
```bash
az account get-access-token > /dev/null && echo "Token refreshed"
```

Check what resources you can access:
```bash
make show-env ENV_NAME=nlweb-dev-centralus
```

## Development Workflows

### Ask API Development

```bash
cd ask_api

# Run locally on port 8000
make dev

# Run tests
make test

# Build and deploy to AKS
make build    # Builds to ACR
make deploy   # Deploys via Helm
```

**API Endpoints:**
- `GET/POST /ask` - Query endpoint
- `GET /health` - Health check
- `POST /mcp` - Model Context Protocol
- `POST /a2a` - Agent-to-Agent protocol

### Crawler Development

```bash
cd crawler

# Run master (API + scheduler) on port 5001
make dev-master

# In a separate terminal, run a worker
make dev-worker

# Run tests
make test

# Build and deploy to AKS
make build && make deploy
```

**Crawler Endpoints:**
- `GET /` - Web UI
- `GET /api/status` - System status
- `POST /api/sites` - Add site to crawl
- `GET /api/queue/status` - Queue statistics

**Check database counts:**
```bash
uv run python count_items.py
```

### Docker Development

Both services support Docker Compose:

```bash
# Ask API
cd ask_api
make docker-up

# Crawler
cd crawler
make docker-up
```

## Architecture

### Ask API

**Config-driven provider system** (`ask_api/config.yaml`):
- Pluggable providers for LLM, embeddings, vector DB, object storage
- Workspace structure with modular packages:
  - `nlweb-core` - Framework & orchestration
  - `nlweb-network` - Protocol adapters
  - `nlweb-dataload` - Data loading utilities
  - Provider packages in `packages/providers/`

**Multi-protocol support:**
- HTTP REST with optional SSE streaming
- Model Context Protocol (MCP)
- Agent-to-Agent (A2A) protocol

### Crawler

**Master/worker pattern:**
- Master: Flask API + job scheduler
- Worker: Queue processor
- Flow: Parse sitemaps → queue JSON → embed → upload to Azure AI Search

### Azure Services

| Service | Purpose |
|---------|---------|
| Azure OpenAI | LLM + embeddings |
| Azure AI Search | Vector search |
| Azure Cosmos DB | Object storage & site config |
| Azure SQL Server | Relational data (crawler) |
| Azure Storage | Blobs & queues |
| Azure Key Vault | Secrets management |
| Azure Container Registry | Docker images |
| Azure Kubernetes Service | Container orchestration |

## Infrastructure Deployment

From the `/deployment` directory:

```bash
# 1. Login and set environment
make login
export PI_LABS_ENDPOINT=https://...
export PI_LABS_KEY=...

# 2. Deploy Azure infrastructure (~15-20 min)
make deploy ENV_NAME=myenv LOCATION=eastus2

# 3. Setup Kubernetes (cert-manager, KEDA, ALB, Gateway)
make setup-k8s ENV_NAME=myenv

# 4. Build Docker images
make build-images ENV_NAME=myenv

# 5. Deploy application
make install-nlweb ENV_NAME=myenv

# 6. (Optional) Enable TLS
make request-certificate HOSTNAME=app.example.com
make check-certificate
make enable-tls ENV_NAME=myenv
```

## Common Tasks

### Check Deployment Status

```bash
# Helm releases
make status

# Pod logs
cd ask_api && make logs
cd crawler && make logs-master
cd crawler && make logs-worker

# Port forwarding
cd ask_api && make port-forward    # localhost:8000
cd crawler && make port-forward    # localhost:5001
```

### Update a Service

```bash
# After making code changes
cd ask_api  # or crawler
make build    # Build new image to ACR
make deploy   # Deploy to AKS with new image
```

### Switch Environments

Edit the `ENV_NAME` variable in:
- `crawler/Makefile` line 7
- `common.mk` line 5 (default for all)

Or override per command:
```bash
make init_environment ENV_NAME=nlweb-yoast-centralus
```

## Troubleshooting

### Permission Errors

**Problem:** `AuthorizationFailed` or `Forbidden` errors

**Solution:**
1. Check resource group access: `az group show -n rg-nlweb-dev-centralus`
2. Check Key Vault access: Needs "Key Vault Secrets User" role
3. Refresh token: `az account get-access-token > /dev/null`
4. Wait 5-10 minutes for permission propagation

### Empty .env File

**Problem:** `.env` created but secrets are empty/error messages

**Solution:**
- Verify Key Vault permissions (RBAC role assignment)
- Check Key Vault name with: `make show-env`
- Ensure you're targeting the correct environment

### Database Out of Sync

**Problem:** Vector DB and SQL Server have different counts

**Solution:**
- This is expected during active crawling
- Vector DB typically has more items (includes all embedded content)
- SQL Server tracks unique document IDs

### Cosmos DB Not Configured

**Problem:** `count_items.py` shows "Cosmos DB: Not configured"

**Solution:**
- Environment variable mismatch in the script
- Script expects `AZURE_COSMOS_ENDPOINT` but .env has `COSMOS_DB_ENDPOINT`
- Can be ignored if not actively using Cosmos DB for crawler

## Testing

### Local Tests

```bash
# Ask API
cd ask_api
uv run pytest

# Crawler
cd crawler
uv run pytest code/tests/
```

### CI/CD

GitHub Actions runs on PRs to main (`.github/workflows/analyze.yml`):
1. `uv sync` in ask_api
2. `pytest` in ask_api

## Project Structure

```
nlweb-ask-agent/
├── ask_api/              # Semantic search API
│   ├── packages/         # Modular workspace packages
│   │   ├── core/        # Framework & orchestration
│   │   ├── network/     # Protocol adapters
│   │   ├── dataload/    # Data loading
│   │   └── providers/   # Provider implementations
│   ├── config.yaml      # Provider configuration
│   └── Makefile         # Development commands
├── crawler/              # Web crawler service
│   ├── code/core/       # Core crawler logic
│   ├── testing/         # Test utilities
│   └── Makefile         # Development commands
├── deployment/           # Infrastructure as Code
│   ├── bicep/           # Bicep templates
│   └── Makefile         # Deployment commands
├── helm/                # Kubernetes Helm charts
│   ├── gateway/         # Gateway infrastructure chart
│   ├── ask-api/         # Ask API chart
│   ├── chat-app/        # Chat App chart
│   └── crawler/         # Crawler chart
├── common.mk            # Shared Makefile functions
└── CLAUDE.md            # AI assistant guidance
```

## Adding New Providers

1. Create package: `ask_api/packages/providers/<provider>/`
2. Implement required interface (LLM, embedding, retrieval, etc.)
3. Add workspace entry to `ask_api/pyproject.toml`
4. Update `ask_api/config.yaml` with `import_path` and `class_name`

## Quick Reference Commands

```bash
# Development
make dev                  # Run service locally
make test                 # Run tests
make docker-up            # Run in Docker

# Deployment
make build                # Build to ACR
make deploy               # Deploy to AKS
make logs                 # Stream logs
make port-forward         # Forward port to local

# Infrastructure
make show-env             # Show discovered resources
make init_environment     # Pull secrets from Key Vault

# Crawler specific
uv run python count_items.py  # Check database counts
```

## Useful Resources

- [uv Documentation](https://docs.astral.sh/uv/)
- [Azure CLI Documentation](https://docs.microsoft.com/cli/azure/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- Project docs: Individual package READMEs in each directory
