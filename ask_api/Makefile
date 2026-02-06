# Ask API Makefile
# For AKS deployment, uses environment-based resource discovery
include ../common.mk

.PHONY: dev build deploy down port-forward logs test lint format typecheck check init_environment build-llm-scoring deploy-llm-scoring down-llm-scoring logs-llm-scoring

dev:
	uv run run_server.py

# Build Docker image to ACR
build:
	$(call discover-azure-resources)
	$(call validate-azure-resources)
	az acr build \
		--registry $(ACR_LOGIN_SERVER) \
		--image ask-api:latest \
		--file Dockerfile \
		.

# Deploy to AKS using Helm (upgrades ask-api image only)
deploy:
	$(call discover-azure-resources)
	$(call validate-azure-resources)
	$(call aks-login)
	$(eval DIGEST := $(shell az acr manifest list-metadata --registry $(ACR_NAME) --name ask-api --query "[?tags[?@=='latest']].digest | [0]" -o tsv))
	helm upgrade ask-api ../helm/ask-api \
		--set image.tag=$(DIGEST) \
		--reuse-values
	@echo ""
	@echo "Deployed to: https://$$(kubectl get gateway -n gateway nlweb-gateway -o jsonpath='{.status.addresses[0].value}' 2>/dev/null || echo '<gateway not found>')/"

# Remove ask-api from AKS
down:
	$(call discover-azure-resources)
	$(call aks-login)
	helm uninstall ask-api

port-forward:
	kubectl port-forward -n ask-api svc/ask-api-service 8000:8000

logs:
	kubectl logs -n ask-api -l app=ask-api -f

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .
	uv run ruff check --fix --select I .

typecheck:
	uv run pyright

check: lint typecheck test

# Pull secrets from Azure Key Vault to .env for local development
init_environment:
	$(call discover-azure-resources)
	@echo "Pulling secrets from Azure Key Vault ($(KEYVAULT_NAME))..."
	@echo "# Auto-generated from Azure Key Vault ($(KEYVAULT_NAME))" > .env
	@echo "# Generated on $$(date)" >> .env
	@echo "" >> .env
	@echo "# Azure OpenAI" >> .env
	@echo "AZURE_OPENAI_ENDPOINT=$$(az keyvault secret show --vault-name $(KEYVAULT_NAME) --name AZURE-OPENAI-ENDPOINT --query value -o tsv)" >> .env
	@echo "AZURE_OPENAI_KEY=$$(az keyvault secret show --vault-name $(KEYVAULT_NAME) --name AZURE-OPENAI-KEY --query value -o tsv)" >> .env
	@echo "" >> .env
	@echo "# Azure Cognitive Search" >> .env
	@echo "AZURE_SEARCH_ENDPOINT=$$(az keyvault secret show --vault-name $(KEYVAULT_NAME) --name AZURE-SEARCH-ENDPOINT --query value -o tsv)" >> .env
	@echo "AZURE_SEARCH_KEY=$$(az keyvault secret show --vault-name $(KEYVAULT_NAME) --name AZURE-SEARCH-KEY --query value -o tsv)" >> .env
	@echo "AZURE_SEARCH_INDEX_NAME=$$(az keyvault secret show --vault-name $(KEYVAULT_NAME) --name AZURE-SEARCH-INDEX-NAME --query value -o tsv)" >> .env
	@echo "" >> .env
	@echo "# Azure Cosmos DB" >> .env
	@echo "COSMOS_DB_ENDPOINT=$$(az keyvault secret show --vault-name $(KEYVAULT_NAME) --name COSMOS-DB-ENDPOINT --query value -o tsv)" >> .env
	@echo "COSMOS_DB_DATABASE_NAME=$$(az keyvault secret show --vault-name $(KEYVAULT_NAME) --name COSMOS-DB-DATABASE-NAME --query value -o tsv)" >> .env
	@echo "COSMOS_DB_CONTAINER_NAME=$$(az keyvault secret show --vault-name $(KEYVAULT_NAME) --name COSMOS-DB-CONTAINER-NAME --query value -o tsv)" >> .env
	@echo "" >> .env
	@echo "# Pi Labs" >> .env
	@echo "PI_LABS_ENDPOINT=$$(az keyvault secret show --vault-name $(KEYVAULT_NAME) --name PI-LABS-ENDPOINT --query value -o tsv)" >> .env
	@echo "PI_LABS_KEY=$$(az keyvault secret show --vault-name $(KEYVAULT_NAME) --name PI-LABS-KEY --query value -o tsv)" >> .env
	@echo "" >> .env
	@echo ".env file created."

# ============================================================================
# LLM Scoring Deployment (separate deployment with Azure OpenAI scoring)
# ============================================================================

# Build Docker image for llm-scoring deployment
build-llm-scoring:
	$(call discover-azure-resources)
	$(call validate-azure-resources)
	az acr build \
		--registry $(ACR_LOGIN_SERVER) \
		--image ask-api:llm-scoring \
		--build-arg CONFIG_FILE=config-llm-scoring.yaml \
		--file Dockerfile \
		.

# Deploy llm-scoring to AKS using Helm (creates/updates ask-api-llm-scoring release)
deploy-llm-scoring:
	$(call discover-azure-resources)
	$(call validate-azure-resources)
	$(call aks-login)
	$(eval DIGEST := $(shell az acr manifest list-metadata --registry $(ACR_NAME) --name ask-api --query "[?tags[?@=='llm-scoring']].digest | [0]" -o tsv))
	@echo "Getting values from production deployment..."
	$(eval WORKLOAD_IDENTITY := $(shell helm get values ask-api -o json | jq -r '.workloadIdentity.clientId'))
	$(eval KEYVAULT_NAME := $(shell helm get values ask-api -o json | jq -r '.global.keyVault.name'))
	$(eval KEYVAULT_TENANT := $(shell helm get values ask-api -o json | jq -r '.global.keyVault.tenantId'))
	$(eval ACR_SERVER := $(shell helm get values ask-api -o json | jq -r '.global.containerRegistry.server'))
	helm upgrade --install ask-api-llm-scoring ../helm/ask-api \
		--set createNamespace=false \
		--set createServiceAccount=false \
		--set image.tag=$(DIGEST) \
		--set routing.pathPrefix="/llm-scoring" \
		--set serviceAccount.name=ask-api-sa \
		--set workloadIdentity.clientId=$(WORKLOAD_IDENTITY) \
		--set global.keyVault.name=$(KEYVAULT_NAME) \
		--set global.keyVault.tenantId=$(KEYVAULT_TENANT) \
		--set global.containerRegistry.server=$(ACR_SERVER)
	@echo ""
	@echo "Deployed llm-scoring to: https://$$(kubectl get gateway -n gateway nlweb-gateway -o jsonpath='{.status.addresses[0].value}' 2>/dev/null || echo '<gateway not found>')/llm-scoring"

# Remove llm-scoring deployment from AKS
down-llm-scoring:
	$(call discover-azure-resources)
	$(call aks-login)
	helm uninstall ask-api-llm-scoring

# View logs for llm-scoring deployment
logs-llm-scoring:
	kubectl logs -n ask-api -l app=ask-api,app.kubernetes.io/instance=ask-api-llm-scoring -f
