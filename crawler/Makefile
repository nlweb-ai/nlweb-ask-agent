# Crawler Makefile
# For AKS deployment, uses environment-based resource discovery
include ../common.mk

.DEFAULT_GOAL := help

.PHONY: help dev test lint format typecheck check build deploy down logs init_environment

# ==============================================================================
# Help
# ==============================================================================

help:
	@echo "Crawler"
	@echo ""
	@echo "Development:"
	@echo "  make dev              Run locally with Docker Compose"
	@echo "  make test             Run test suite"
	@echo "  make lint             Run linter"
	@echo "  make format           Format code"
	@echo "  make typecheck        Run type checker"
	@echo "  make check            Run all checks (lint, format, typecheck, test)"
	@echo ""
	@echo "Deployment:"
	@echo "  make build            Build Docker image to ACR"
	@echo "  make deploy           Deploy to AKS"
	@echo "  make down             Uninstall from AKS"
	@echo "  make logs             Tail AKS pod logs"
	@echo ""
	@echo "Setup:"
	@echo "  make init_environment Generate .env from Azure Key Vault"
	@echo ""
	@echo "Options:"
	@echo "  ENV_NAME=<name>       Azure environment (default: $(ENV_NAME))"

# ==============================================================================
# Development
# ==============================================================================

dev:
	docker compose -f ../docker-compose.yml up --build crawler-master crawler-worker

# ==============================================================================
# Code Quality
# ==============================================================================

test:
	uv run pytest code/tests/ -vv

lint:
	uv run ruff check .

format:
	uv run ruff format .
	uv run ruff check --fix --select I .

typecheck:
	uv run pyright

check: lint format typecheck test

# ==============================================================================
# Deployment
# ==============================================================================

build:
	$(call discover-azure-resources)
	$(call validate-azure-resources)
	az acr build \
		--registry $(ACR_LOGIN_SERVER) \
		--image crawler:latest \
		--file Dockerfile \
		.

deploy:
	$(call discover-azure-resources)
	$(call validate-azure-resources)
	$(call aks-login)
	$(eval DIGEST := $(shell az acr manifest list-metadata --registry $(ACR_NAME) --name crawler --query "[?tags[?@=='latest']].digest | [0]" -o tsv))
	helm upgrade crawler ../helm/crawler \
		--set image.tag=$(DIGEST) \
		--reuse-values
	@echo ""
	@echo "Deployed to: https://$$(kubectl get gateway -n gateway nlweb-gateway -o jsonpath='{.status.addresses[0].value}' 2>/dev/null || echo '<gateway not found>')/crawler/"

down:
	$(call discover-azure-resources)
	$(call aks-login)
	helm uninstall crawler

logs:
	kubectl logs -n crawler -l app.kubernetes.io/instance=crawler -f

# ==============================================================================
# Setup
# ==============================================================================

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
