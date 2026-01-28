# NLWeb Infrastructure Deployment
# Deploys baseline Azure infrastructure for ask_api and crawler

include ../common.mk

.PHONY: help login deploy destroy validate show-outputs grant-app-access setup-k8s build-images install-nlweb request-certificate check-certificate enable-tls load-synthetic

# Deployment-specific options
LOCATION ?= centralus
COSMOS_LOCATION ?=
SQL_LOCATION ?=
CERT_MANAGER_EMAIL ?= admin@nlweb.ai

help:
	@echo "NLWeb Infrastructure Deployment"
	@echo ""
	@echo "Usage:"
	@echo "  make login             - Login to Azure CLI"
	@echo "  make validate          - Validate Bicep templates without deploying"
	@echo "  make deploy            - Deploy Azure infrastructure (Bicep)"
	@echo "  make setup-k8s         - Setup K8s infrastructure (cert-manager, KEDA, ALB, Gateway)"
	@echo "  make build-images      - Build Docker images via ACR Tasks"
	@echo "  make install-nlweb     - Deploy application (does not build images)"
	@echo "  make request-certificate - Request TLS certificate from Let's Encrypt"
	@echo "  make check-certificate - Check certificate and secret status"
	@echo "  make enable-tls        - Enable TLS on the Gateway (does not touch application)"
	@echo "  make grant-app-access  - Grant an app/managed identity access to resources"
	@echo "  make load-synthetic    - Load synthetic schema data into crawler"
	@echo "  make destroy           - Delete all deployed resources"
	@echo "  make show-env          - Show discovered Azure resources"
	@echo ""
	@echo "Required environment variables:"
	@echo "  PI_LABS_ENDPOINT         - PI Labs AzureML endpoint URL"
	@echo "  PI_LABS_KEY              - PI Labs API key"
	@echo ""
	@echo "Options:"
	@echo "  ENV_NAME=<name>          - Environment name (default: $(ENV_NAME))"
	@echo "  LOCATION=<region>        - Azure region (default: $(LOCATION))"
	@echo "  COSMOS_LOCATION=<region> - Cosmos DB region (defaults to LOCATION)"
	@echo "  SQL_LOCATION=<region>    - SQL Server region (defaults to LOCATION)"
	@echo "  CERT_MANAGER_EMAIL=<email> - Let's Encrypt email for setup-k8s"
	@echo ""
	@echo "Examples:"
	@echo "  export PI_LABS_ENDPOINT=https://... PI_LABS_KEY=..."
	@echo "  make deploy ENV_NAME=prod LOCATION=swedencentral"
	@echo "  make setup-k8s ENV_NAME=prod"
	@echo "  make build-images ENV_NAME=prod"
	@echo "  make install-nlweb ENV_NAME=prod"
	@echo "  make request-certificate HOSTNAME=app.example.com"
	@echo "  make enable-tls ENV_NAME=prod"
	@echo "  make destroy ENV_NAME=prod"

login:
	az login

validate:
	@echo "Validating Bicep templates..."
	az bicep build --file infra/main.bicep
	@rm -f infra/main.json
	@echo "Validation successful!"

deploy: validate
	@if [ -z "$$PI_LABS_ENDPOINT" ]; then \
		echo "Error: PI_LABS_ENDPOINT environment variable is required"; \
		exit 1; \
	fi
	@if [ -z "$$PI_LABS_KEY" ]; then \
		echo "Error: PI_LABS_KEY environment variable is required"; \
		exit 1; \
	fi
	@echo "Deploying infrastructure..."
	@echo "  Environment: $(ENV_NAME)"
	@echo "  Location: $(LOCATION)"
	@if [ -n "$(COSMOS_LOCATION)" ]; then echo "  Cosmos Location: $(COSMOS_LOCATION)"; fi
	@if [ -n "$(SQL_LOCATION)" ]; then echo "  SQL Location: $(SQL_LOCATION)"; fi
	@if [ -n "$(APP_PRINCIPAL_ID)" ]; then echo "  App Principal: $(APP_PRINCIPAL_ID)"; fi
	@echo ""
	az deployment sub create \
		--name "nlweb-$(ENV_NAME)-$$(date +%Y%m%d%H%M%S)" \
		--location $(LOCATION) \
		--template-file infra/main.bicep \
		--parameters environmentName=$(ENV_NAME) \
		--parameters location=$(LOCATION) \
		--parameters principalId=$$(az ad signed-in-user show --query id -o tsv 2>/dev/null || echo "") \
		$(if $(COSMOS_LOCATION),--parameters cosmosLocation=$(COSMOS_LOCATION),) \
		$(if $(SQL_LOCATION),--parameters sqlLocation=$(SQL_LOCATION),) \
		$(if $(APP_PRINCIPAL_ID),--parameters appPrincipalId=$(APP_PRINCIPAL_ID),) \
		--parameters piLabsEndpoint="$$PI_LABS_ENDPOINT" \
		--parameters piLabsKey="$$PI_LABS_KEY" \
		--output table
	@echo ""
	@echo "=== Azure Infrastructure Deployed ==="
	@echo ""
	@echo "Next step: Setup Kubernetes infrastructure (cert-manager, KEDA, ALB, Gateway)"
	@echo "  make setup-k8s ENV_NAME=$(ENV_NAME)"
	@echo ""

destroy:
	@echo "This will delete the resource group '$(RG_NAME)' and ALL resources in it."
	@read -p "Are you sure? (yes/no): " confirm && [ "$$confirm" = "yes" ] || (echo "Aborted." && exit 1)
	az group delete --name $(RG_NAME) --yes --no-wait
	@echo "Resource group deletion initiated. This may take several minutes."

# Grant an application/managed identity access to all resources
# Usage: make grant-app-access ENV_NAME=myenv APP_PRINCIPAL_ID=<guid>
APP_PRINCIPAL_ID ?=
grant-app-access:
	@if [ -z "$(APP_PRINCIPAL_ID)" ]; then \
		echo "Error: APP_PRINCIPAL_ID is required"; \
		echo "Usage: make grant-app-access ENV_NAME=$(ENV_NAME) APP_PRINCIPAL_ID=<managed-identity-principal-id>"; \
		exit 1; \
	fi
	@echo "Granting access to principal: $(APP_PRINCIPAL_ID)"
	@echo "Resource group: $(RG_NAME)"
	az deployment group create \
		--name "grant-access-$$(date +%Y%m%d%H%M%S)" \
		--resource-group $(RG_NAME) \
		--template-file infra/modules/roles.bicep \
		--parameters principalId=$(APP_PRINCIPAL_ID) \
		--parameters principalType=ServicePrincipal \
		--parameters cosmosAccountId=$$(az cosmosdb list -g $(RG_NAME) --query "[0].id" -o tsv) \
		--parameters storageAccountId=$$(az storage account list -g $(RG_NAME) --query "[0].id" -o tsv) \
		--parameters openAiAccountId=$$(az cognitiveservices account list -g $(RG_NAME) --query "[0].id" -o tsv) \
		--parameters searchServiceId=$$(az search service list -g $(RG_NAME) --query "[0].id" -o tsv) \
		--output table
	@echo ""
	@echo "Access granted successfully!"

# Setup Kubernetes infrastructure (cert-manager, KEDA, ALB controller, Gateway)
# Usage: make setup-k8s ENV_NAME=myenv
setup-k8s:
	@echo "Setting up Kubernetes infrastructure..."
	@echo "  Environment: $(ENV_NAME)"
	@echo ""
	$(call discover-azure-resources)
	$(call validate-azure-resources)
	@echo "  Resource Group: $(RG_NAME)"
	@echo "  AKS: $(AKS_NAME)"
	@echo ""
	AZURE_RESOURCE_GROUP=$(RG_NAME) \
	AKS_NAME=$(AKS_NAME) \
	ALB_SUBNET_ID=$(ALB_SUBNET) \
	KEDA_IDENTITY_CLIENT_ID=$(KEDA_ID) \
	ALB_CONTROLLER_IDENTITY_CLIENT_ID=$(ALB_CONTROLLER_ID) \
	AZURE_TENANT_ID=$(TENANT_ID) \
	AZURE_CERT_MANAGER_EMAIL=$(CERT_MANAGER_EMAIL) \
	./scripts/setup_k8s.sh

# Build images via ACR Tasks
# Usage: make build-images ENV_NAME=myenv
build-images:
	@echo "Building images via ACR Tasks..."
	@echo "  Environment: $(ENV_NAME)"
	@echo ""
	$(call discover-azure-resources)
	$(call validate-azure-resources)
	@echo "  ACR: $(ACR_NAME)"
	@echo ""
	ACR_NAME=$(ACR_NAME) ./scripts/build_images.sh

# Install application Helm chart on AKS (does not build images)
# Gateway must be installed first via setup-k8s
# Usage: make install-nlweb ENV_NAME=myenv
install-nlweb:
	@echo "Deploying application to AKS..."
	@echo "  Environment: $(ENV_NAME)"
	@echo ""
	$(call discover-azure-resources)
	$(call validate-azure-resources)
	@echo "  Resource Group: $(RG_NAME)"
	@echo "  ACR: $(ACR_NAME)"
	@echo "  AKS: $(AKS_NAME)"
	@echo ""
	AZURE_RESOURCE_GROUP=$(RG_NAME) \
	ACR_NAME=$(ACR_NAME) \
	AKS_NAME=$(AKS_NAME) \
	ACR_LOGIN_SERVER=$(ACR_LOGIN_SERVER) \
	AZURE_KEYVAULT_NAME=$(KEYVAULT_NAME) \
	STORAGE_ACCOUNT_NAME=$(STORAGE_NAME) \
	ASK_API_IDENTITY_CLIENT_ID=$(ASK_API_ID) \
	CRAWLER_IDENTITY_CLIENT_ID=$(CRAWLER_ID) \
	KEDA_IDENTITY_CLIENT_ID=$(KEDA_ID) \
	AZURE_TENANT_ID=$(TENANT_ID) \
	./scripts/deploy_aks.sh

# Request a TLS certificate from Let's Encrypt
# Prereqs: Gateway deployed in HTTP mode, DNS configured to point to ALB
# Usage: make request-certificate HOSTNAME=app.example.com
HOSTNAME ?=
request-certificate:
	@if [ -z "$(HOSTNAME)" ]; then \
		echo "Error: HOSTNAME is required"; \
		echo "Usage: make request-certificate HOSTNAME=app.example.com"; \
		exit 1; \
	fi
	@echo "Requesting TLS certificate for: $(HOSTNAME)"
	@echo ""
	@echo "Prerequisites:"
	@echo "  1. Gateway must be deployed in HTTP mode (no TLS_SECRET_NAME)"
	@echo "  2. DNS must be configured to point to the ALB FQDN"
	@echo ""
	cat manifests/certificate.yaml | sed "s/\$${HOSTNAME}/$(HOSTNAME)/g" | kubectl apply -f -
	@echo ""
	@echo "Certificate requested. Check status with: make check-certificate"

# Check certificate and secret status
check-certificate:
	@echo "=== Certificate Status ==="
	kubectl get certificate -n gateway
	@echo ""
	@echo "=== Certificate Details ==="
	kubectl describe certificate nlweb-tls-cert -n gateway 2>/dev/null || echo "Certificate not found"
	@echo ""
	@echo "=== TLS Secret Status ==="
	@kubectl get secret nlweb-tls-secret -n gateway 2>/dev/null && \
		(echo ""; echo "=== Next Step ==="; echo "TLS secret is ready! Enable TLS on the Gateway:"; echo "  make enable-tls ENV_NAME=<env>") || \
		echo "TLS secret not yet available. Wait for certificate to be issued."

# Enable TLS on the Gateway - delegates to setup-k8s (which auto-detects TLS secret)
# This does NOT touch the application (ask-api, crawler)
# Usage: make enable-tls ENV_NAME=myenv
enable-tls:
	@echo "Enabling TLS on Gateway..."
	@kubectl get secret nlweb-tls-secret -n gateway >/dev/null 2>&1 || \
		(echo "Error: TLS secret 'nlweb-tls-secret' not found. Run 'make request-certificate' first and wait for it to be ready." && exit 1)
	@echo "TLS secret found. Upgrading Gateway..."
	$(MAKE) setup-k8s

# Load synthetic schema data into crawler
# Downloads index.json from synthetic data storage and adds each site/sitemap pair
# Usage: make load-synthetic HOSTNAME=<host> SPLIT_NAME=<split>
SPLIT_NAME ?=
load-synthetic:
	@if [ -z "$(HOSTNAME)" ]; then \
		echo "Error: HOSTNAME is required"; \
		echo "Usage: make load-synthetic HOSTNAME=<crawler-hostname> SPLIT_NAME=<split-name>"; \
		exit 1; \
	fi
	@if [ -z "$(SPLIT_NAME)" ]; then \
		echo "Error: SPLIT_NAME is required"; \
		echo "Usage: make load-synthetic HOSTNAME=<crawler-hostname> SPLIT_NAME=<split-name>"; \
		exit 1; \
	fi
	@echo "Loading synthetic data..."
	@echo "  Hostname: $(HOSTNAME)"
	@echo "  Split: $(SPLIT_NAME)"
	@echo ""
	HOSTNAME=$(HOSTNAME) SPLIT_NAME=$(SPLIT_NAME) ./scripts/load_synthetic.sh
