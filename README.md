# NLWeb Ask Agent

Distributed question-answering system with semantic search over crawled web content.

## Prerequisites

- [Python 3.12](https://www.python.org/downloads/)
- [uv](https://docs.astral.sh/uv/) - Python package manager
- [Node.js](https://nodejs.org/) (LTS)
- [pnpm](https://pnpm.io/installation) - Frontend package manager
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Helm](https://helm.sh/docs/intro/install/) - Kubernetes package manager
- [Azure CLI](https://docs.microsoft.com/cli/azure/install-azure-cli) 2.50+

## Quick Start

Each service needs credentials from Azure Key Vault. You need **Reader** access on
the resource group and **Key Vault Secrets User** on the Key Vault.

```bash
# Generate .env files for ask-api and crawler
make init_environment

# Start ask-api + chat-app (with HMR)
make ask
# → ask-api: http://localhost:8000
# → chat-app: http://localhost:5173
```

To target a specific environment:
```bash
make init_environment ENV_NAME=nlweb-yoast-centralus
```

## Running Locally

```bash
make ask          # Ask API + Chat App
make fullstack    # Full stack (+ crawler)
make check        # Run all checks across all modules
```

Each service directory (`ask_api/`, `crawler/`, `frontend/`) has the same Makefile targets:

```bash
cd ask_api   # or crawler, or frontend
make dev     # Run with Docker Compose
make test    # Run tests
make check   # Run all checks (lint, format, typecheck, test)
```

## Deploying Code Changes

```bash
cd ask_api   # or crawler, or frontend
make build   # Build Docker image to ACR
make deploy  # Deploy to AKS via Helm
```

Or deploy everything at once from the repo root:

```bash
make build-all   # Build all images
make deploy-all  # Deploy all services
```

## Infrastructure

See [deployment/README.md](deployment/README.md) for provisioning Azure
infrastructure from scratch.

## Project Structure

```
nlweb-ask-agent/
├── ask_api/              # Semantic search API
│   ├── packages/
│   │   ├── core/         # Framework & orchestration
│   │   ├── network/      # Protocol adapters (HTTP/MCP/A2A)
│   │   └── providers/    # Provider implementations
│   └── config.yaml       # Provider configuration
├── crawler/              # Web crawler (master/worker)
├── frontend/             # pnpm workspace
│   ├── chat-app/         # React chat UI
│   └── search-components/# Shared component library
├── deployment/           # Azure Bicep templates & scripts
│   └── infra/            # Bicep modules
├── helm/                 # Kubernetes Helm charts
│   ├── gateway/          # Gateway infrastructure
│   ├── ask-api/          # Ask API
│   ├── chat-app/         # Chat App
│   └── crawler/          # Crawler
└── common.mk             # Shared Makefile variables
```
