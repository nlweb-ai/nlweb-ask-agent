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

## Prerequisites

- [Azure CLI](https://docs.microsoft.com/cli/azure/install-azure-cli) (2.50+)
- [GitHub CLI](https://cli.github.com/) (for npm authentication)
- Azure subscription with OpenAI access enabled
- `PI_LABS_ENDPOINT` and `PI_LABS_KEY` environment variables

## Bringing Up a New Environment

Run these commands in sequence:

```bash
# 1. Login to Azure
make login

# 2. Set required environment variables
# Please acquire the Pi Lab keys from your admin
export PI_LABS_ENDPOINT=https://...
export PI_LABS_KEY=...

# 3. Deploy Azure infrastructure (~15-20 min)
# Please set the environment to your desired name
make deploy ENV_NAME=myenv LOCATION=eastus2

# 4. Setup Kubernetes infrastructure (cert-manager, KEDA, ALB, Gateway)
# Pre-req: Make sure to install helm before running this command
make setup-k8s ENV_NAME=myenv

# 5. Build Docker images via ACR Tasks
make build-images ENV_NAME=myenv

# 6. Deploy application to AKS
# Make sure docker is installed and running
make install-nlweb ENV_NAME=myenv

# 7. (Optional) Enable TLS
#    First, configure DNS to point to the ALB FQDN shown by setup-k8s
make request-certificate HOSTNAME=app.example.com
make check-certificate    # wait until TLS secret is ready
make enable-tls ENV_NAME=myenv
```

## Available Commands

| Command | Description |
|---------|-------------|
| `make login` | Login to Azure CLI |
| `make validate` | Validate Bicep templates |
| `make deploy` | Deploy Azure infrastructure |
| `make setup-k8s` | Setup K8s (cert-manager, KEDA, ALB, Gateway) |
| `make build-images` | Build Docker images via ACR Tasks |
| `make install-nlweb` | Deploy application to AKS |
| `make request-certificate` | Request TLS cert from Let's Encrypt |
| `make check-certificate` | Check certificate status |
| `make enable-tls` | Enable TLS on Gateway |
| `make grant-app-access` | Grant identity access to resources |
| `make destroy` | Delete all resources |

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `ENV_NAME` | `nlweb-yoast-centralus` | Environment name (used in resource naming) |
| `LOCATION` | `centralus` | Azure region |
| `COSMOS_LOCATION` | (same as LOCATION) | Cosmos DB region override |
| `SQL_LOCATION` | (same as LOCATION) | SQL Server region override |
| `CERT_MANAGER_EMAIL` | `admin@nlweb.ai` | Let's Encrypt notification email |
| `HOSTNAME` | (required for TLS) | Domain for TLS certificate |

## Cleanup

```bash
make destroy ENV_NAME=myenv
```

This deletes the resource group and all resources within it.
