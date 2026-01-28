SHELL := /bin/bash

# Crawler Makefile
# For AKS deployment, uses environment-based resource discovery

include ../common.mk

.PHONY: help dev-master dev-worker env-check test build deploy down port-forward logs-master logs-worker init_environment

DEFAULT_GOAL := help

help:
	@echo "Makefile commands:"
	@echo "  make dev-master        # Run master (API + scheduler)"
	@echo "  make dev-worker        # Run a worker process"
	@echo "  make test              # Run local test suite (unit tests)"
	@echo "  make build             # Build Docker image to ACR"
	@echo "  make deploy            # Deploy to AKS using Helm"
	@echo "  make down              # Disable crawler in AKS"
	@echo "  make port-forward      # Forward localhost:5001 to crawler-master-service"
	@echo "  make logs-master       # Stream master pod logs"
	@echo "  make logs-worker       # Stream worker pod logs"
	@echo "  make init_environment  # Pull secrets from Azure Key Vault to .env"
	@echo "  make env-check         # Ensure .env exists"
	@echo ""
	@echo "Environment options:"
	@echo "  ENV_NAME=<name>        # Target environment (default: $(ENV_NAME))"

dev-master: env-check
	@echo "Starting master..."
	@uv run testing/start_api_server.py

dev-worker: env-check
	@echo "Starting worker..."
	@uv run testing/start_worker.py

env-check:
	@if [ -f .env ]; then \
		echo ".env found"; \
	else \
		echo "WARNING: .env not found - run make init_environment"; exit 1; \
	fi

test:
	@echo "Running local test suite..."
	@echo ""
	@echo "Running unit tests..."
	@uv run pytest code/tests/ -vv

# Build single unified image
build:
	$(call discover-azure-resources)
	$(call validate-azure-resources)
	@echo "Building Docker image..."
	az acr build \
		--registry $(ACR_LOGIN_SERVER) \
		--image crawler:latest \
		--file Dockerfile \
		.

# Deploy to AKS using Helm (upgrades crawler image only)
deploy:
	$(call discover-azure-resources)
	$(call validate-azure-resources)
	$(call aks-login)
	$(eval DIGEST := $(shell az acr manifest list-metadata --registry $(ACR_NAME) --name crawler --query "[?tags[?@=='latest']].digest | [0]" -o tsv))
	helm upgrade nlweb ../helm/nlweb \
		--set crawler.image.tag=$(DIGEST) \
		--reuse-values
	@echo ""
	@echo "Deployed to: https://$$(kubectl get gateway -n gateway nlweb-gateway -o jsonpath='{.status.addresses[0].value}' 2>/dev/null || echo '<gateway not found>')/crawler/"

# Disable crawler in AKS
down:
	$(call discover-azure-resources)
	$(call aks-login)
	helm upgrade nlweb ../helm/nlweb \
		--set crawler.enabled=false \
		--reuse-values

port-forward:
	kubectl port-forward -n crawler svc/nlweb-crawler-master-service 5001:5001

logs-master:
	kubectl logs -n crawler -l app=crawler-master -f

logs-worker:
	kubectl logs -n crawler -l app=crawler-worker -f

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
	@echo "# SQL Server" >> .env
	@echo "DB_SERVER=$$(az keyvault secret show --vault-name $(KEYVAULT_NAME) --name SQL-SERVER-FQDN --query value -o tsv)" >> .env
	@echo "DB_DATABASE=$$(az keyvault secret show --vault-name $(KEYVAULT_NAME) --name SQL-DATABASE --query value -o tsv)" >> .env
	@echo "DB_USERNAME=$$(az keyvault secret show --vault-name $(KEYVAULT_NAME) --name SQL-USERNAME --query value -o tsv)" >> .env
	@echo "DB_PASSWORD=$$(az keyvault secret show --vault-name $(KEYVAULT_NAME) --name SQL-PASSWORD --query value -o tsv)" >> .env
	@echo "" >> .env
	@echo ".env file created!"
