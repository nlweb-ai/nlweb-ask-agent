# Ask API Makefile
# For AKS deployment, uses environment-based resource discovery
include ../common.mk

.PHONY: dev build deploy down port-forward logs test init_environment

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
	helm upgrade nlweb ../helm/nlweb \
		--set ask-api.image.tag=$(DIGEST) \
		--reuse-values
	@echo ""
	@echo "Deployed to: https://$$(kubectl get gateway -n gateway nlweb-gateway -o jsonpath='{.status.addresses[0].value}' 2>/dev/null || echo '<gateway not found>')/"

# Disable ask-api in AKS
down:
	$(call discover-azure-resources)
	$(call aks-login)
	helm upgrade nlweb ../helm/nlweb \
		--set ask-api.enabled=false \
		--reuse-values

port-forward:
	kubectl port-forward -n ask-api svc/nlweb-ask-api-service 8000:8000

logs:
	kubectl logs -n ask-api -l app=ask-api -f

test:
	uv run pytest

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
