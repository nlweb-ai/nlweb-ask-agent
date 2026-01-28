# NLWeb Ask Agent

Distributed question-answering system with semantic search over crawled web content.

## Components

| Directory | Description |
|-----------|-------------|
| `/ask_api` | REST API with MCP/A2A protocol support |
| `/chat-app` | React frontend |
| `/crawler` | Web crawler for schema.org data |
| `/deployment` | Azure infrastructure (Bicep) |
| `/helm` | Kubernetes Helm charts |

## Quick Start

```bash
# Generate .env files (requires Azure CLI + Key Vault access)
cd ask_api && make init_environment && cd ..
cd crawler && make init_environment && cd ..

# Start frontend (ask-api + chat-app)
export GIT_TOKEN=<github-classic-pat-with-read:packages>
make frontend
```

- Chat UI: http://localhost:5173
- API: http://localhost:8000

## Commands

| Command | Description |
|---------|-------------|
| `make frontend` | Start ask-api + chat-app |
| `make fullstack` | Start all services (+ crawler) |
| `make down` | Stop all services |
| `make logs` | Tail logs |
| `make install` | Deploy to AKS |
| `make status` | Check AKS deployment |

## Requirements

- Docker & Docker Compose
- GitHub PAT with `read:packages` scope (for `@nlweb-ai/search-components`)
- Azure CLI (for `init_environment` and AKS deployment)
