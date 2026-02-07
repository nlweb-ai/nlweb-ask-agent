# Frontend Makefile
# For AKS deployment, uses environment-based resource discovery

include ../common.mk

.PHONY: help dev build deploy down port-forward logs

help:
	@echo "Makefile commands:"
	@echo "  make dev              # Run local development server"
	@echo "  make build            # Build Docker image to ACR"
	@echo "  make deploy           # Deploy to AKS using Helm"
	@echo "  make down             # Remove chat-app from AKS"
	@echo "  make port-forward     # Forward localhost:3000 to chat-app-service"
	@echo "  make logs             # Stream pod logs"
	@echo ""
	@echo "Environment options:"
	@echo "  ENV_NAME=<name>       # Target environment (default: $(ENV_NAME))"

dev:
	pnpm install
	pnpm --filter @nlweb-ai/search-components build
	VITE_ASK_API_URL=https://internal-testing.nlweb.ai pnpm --filter @nlweb-ai/chat-app dev

# Build Docker image to ACR (context is frontend/ for workspace access)
build:
	$(call discover-azure-resources)
	$(call validate-azure-resources)
	az acr build \
		--registry $(ACR_LOGIN_SERVER) \
		--image chat-app:latest \
		.

# Deploy to AKS using Helm (upgrades chat-app image only)
deploy:
	$(call discover-azure-resources)
	$(call validate-azure-resources)
	$(call aks-login)
	$(eval DIGEST := $(shell az acr manifest list-metadata --registry $(ACR_NAME) --name chat-app --query "[?tags[?@=='latest']].digest | [0]" -o tsv))
	helm upgrade chat-app ../helm/chat-app \
		--set image.tag=$(DIGEST) \
		--reuse-values
	@echo ""
	@echo "Deployed to: https://$$(kubectl get gateway -n gateway nlweb-gateway -o jsonpath='{.status.addresses[0].value}' 2>/dev/null || echo '<gateway not found>')/"

# Remove chat-app from AKS
down:
	$(call discover-azure-resources)
	$(call aks-login)
	helm uninstall chat-app

port-forward:
	kubectl port-forward -n chat-app svc/chat-app-service 3000:3000

logs:
	kubectl logs -n chat-app -l app=chat-app -f
