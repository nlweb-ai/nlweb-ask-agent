# NLWeb Ask Agent

Distributed question-answering system with semantic search over crawled web content.

## Components

| Directory | Description |
|-----------|-------------|
| `/ask_api` | REST API with MCP/A2A protocol support |
| `/frontend/chat-app` | React frontend |
| `/frontend/search-components` | Shared React component library |
| `/crawler` | Web crawler for schema.org data |
| `/deployment` | Azure infrastructure (Bicep) |
| `/helm` | Kubernetes Helm charts |

## Quick Start

```bash
# Generate .env files (requires Azure CLI + Key Vault access)
make init_environment

# Install frontend dependencies (pnpm workspace)
cd frontend && pnpm install && cd ..

# Start ask-api + chat-app
make ask
```

- Chat UI: http://localhost:5173
- API: http://localhost:8000

## Commands

| Command | Description |
|---------|-------------|
| `make init_environment` | Generate .env files for ask-api and crawler |
| `make ask` | Start ask-api + chat-app |
| `make fullstack` | Start all services (+ crawler) |
| `make down` | Stop all services |
| `make logs` | Tail logs |

## Requirements

- Docker & Docker Compose
- Node.js + pnpm (for native frontend development)
- Azure CLI (for `init_environment` and AKS deployment)
