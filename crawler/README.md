# Crawler

Distributed web crawler for schema.org structured data.

## Prerequisites

- [Python 3.12](https://www.python.org/downloads/)
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
| `make dev-master` | Run master (API + scheduler) locally |
| `make dev-worker` | Run a worker process locally |
| `make docker-up` | Run under Docker Compose |
| `make build` | Build image to Azure Container Registry |
| `make deploy` | Deploy to AKS via Helm |
| `make test` | Run pytest test suite |

### Other Commands

| Command | Description |
|---------|-------------|
| `make down` | Disable service in AKS |
| `make port-forward` | Forward localhost:5001 to AKS master |
| `make logs-master` | Stream master pod logs |
| `make logs-worker` | Stream worker pod logs |

## API Endpoints

- `GET /` - Web UI
- `GET /api/status` - System status
- `POST /api/sites` - Add site to crawl
- `GET /api/queue/status` - Queue statistics

## Configuration

- `LOG_LEVEL` - Logging level (default: `INFO`)
- `LOG_LEVEL_AZURE` - Azure SDK logging level (default: `WARNING`)
