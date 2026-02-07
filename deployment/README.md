# NLWeb Infrastructure Deployment

Bicep templates for Azure infrastructure required by ask_api and crawler.

## Resources Provisioned

| Resource | Purpose |
|----------|---------|
| Azure OpenAI | LLM + embeddings |
| Azure AI Search | Vector search |
| Azure Cosmos DB | Object storage |
| Azure SQL Server | Relational data |
| Azure Storage | Blob + Queue |
| Azure Key Vault | Secrets management |
| Azure Container Registry | Docker images |
| Azure Kubernetes Service | Container orchestration |
| Azure Managed Grafana | Monitoring dashboards |

## Prerequisites

- [Azure CLI](https://docs.microsoft.com/cli/azure/install-azure-cli) (2.50+)
- [Helm](https://helm.sh/docs/intro/install/) (for Kubernetes setup)
- [Docker](https://docs.docker.com/get-docker/) (for building images)
- Azure subscription with OpenAI access enabled

> **Required: PI Labs Credentials**
>
> You **must** have `PI_LABS_ENDPOINT` and `PI_LABS_KEY` exported in your shell
> before running `make deploy`. The deploy will fail without them. Obtain these
> from your admin.
> ```bash
> export PI_LABS_ENDPOINT=https://...
> export PI_LABS_KEY=...
> ```

## Bringing Up a New Environment

Run these commands in sequence from the `deployment/` directory unless noted otherwise.
Each step prints the exact next command to run when it completes.

```bash
# 1. Login to Azure
make login

# 2. Export PI Labs credentials (required before deploy)
export PI_LABS_ENDPOINT=https://...
export PI_LABS_KEY=...

# 3. Deploy Azure infrastructure (~15-20 min)
make deploy ENV_NAME=myenv LOCATION=eastus2

# 4. Setup Kubernetes infrastructure (cert-manager, KEDA, ALB, Gateway)
#    Wait for the Gateway to get an ADDRESS before proceeding (~5 min)
make setup-k8s ENV_NAME=myenv

# 5. Configure TLS
#    First, point your DNS to the ALB FQDN shown by setup-k8s
make request-certificate HOSTNAME=app.example.com
make check-certificate                              # repeat until TLS secret is ready
make enable-tls ENV_NAME=myenv

# 6. Deploy Grafana dashboards
make deploy-dashboards ENV_NAME=myenv

# 7. Build Docker images (from repo root, not deployment/)
cd .. && make build-all ENV_NAME=myenv

# 8. Deploy application to AKS (from repo root)
make deploy-all ENV_NAME=myenv
```

## Available Commands

### Deployment directory (`deployment/`)

| Command | Description |
|---------|-------------|
| `make login` | Login to Azure CLI |
| `make validate` | Validate Bicep templates |
| `make deploy` | Deploy Azure infrastructure |
| `make setup-k8s` | Setup K8s (cert-manager, KEDA, ALB, Gateway) |
| `make request-certificate` | Request TLS cert from Let's Encrypt |
| `make check-certificate` | Check certificate status |
| `make enable-tls` | Enable TLS on Gateway |
| `make deploy-dashboards` | Deploy Grafana dashboards |
| `make load-synthetic` | Load synthetic schema data into crawler |
| `make show-env` | Show discovered Azure resource names |
| `make destroy` | Delete all resources |

### Repo root

| Command | Description |
|---------|-------------|
| `make build-all` | Build all Docker images to ACR |
| `make deploy-all` | Deploy all services to AKS via Helm |

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `ENV_NAME` | `nlweb-yoast-centralus` | Environment name (used in resource naming) |
| `LOCATION` | `centralus` | Azure region |
| `CERT_MANAGER_EMAIL` | `admin@nlweb.ai` | Let's Encrypt notification email |
| `HOSTNAME` | (required for TLS) | Domain for TLS certificate |

## Cleanup

```bash
make destroy ENV_NAME=myenv
```

This deletes the resource group and all resources within it.
