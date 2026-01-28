# Ask API

REST API for semantic search over crawled content.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Docker](https://www.docker.com/products/docker-desktop/) and docker-compose
- [Azure CLI](https://docs.microsoft.com/cli/azure/install-azure-cli) (for deployment)
- [kubectl](https://kubernetes.io/docs/tasks/tools/) (for deployment)

## Quick Start

1. Set up environment:
   ```bash
   make init_environment   # pulls secrets from Azure Key Vault
   # OR: cp .env.example .env and configure manually
   ```

2. Install dependencies:
   ```bash
   uv sync
   ```

## Development Commands

| Command | Description |
|---------|-------------|
| `make dev` | Run server locally (http://localhost:8000) |
| `make docker-up` | Run under Docker Compose |
| `make build` | Build image to Azure Container Registry |
| `make deploy` | Deploy to AKS via Helm |
| `make test` | Run pytest test suite |

### Other Commands

| Command | Description |
|---------|-------------|
| `make down` | Disable service in AKS |
| `make port-forward` | Forward localhost:8000 to AKS pod |
| `make logs` | Stream pod logs |

## API Endpoints

- `GET/POST /ask` - Query endpoint (params: `query`, `site`, `num_results`, `streaming`)
- `GET /health` - Health check
- `POST /mcp` - MCP JSON-RPC endpoint
- `POST /a2a` - A2A JSON-RPC endpoint
