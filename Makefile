# NLWeb Helm Deployment
# Full stack deployment operations using environment-based resource discovery

include common.mk

.PHONY: help frontend fullstack down logs install upgrade uninstall status

help:
	@echo "NLWeb Development & Deployment"
	@echo ""
	@echo "Local Development:"
	@echo "  make frontend  - Start ask-api (Docker) + chat-app (native)"
	@echo "  make fullstack - Start all services in Docker"
	@echo "  make down      - Stop Docker services"
	@echo "  make logs      - Tail logs from Docker services"
	@echo ""
	@echo "Local Component Development:"
	@echo "  Use 'pnpm link' to link search-components locally"
	@echo ""
	@echo "AKS Deployment:"
	@echo "  make install   - Initial install of full stack to AKS"
	@echo "  make upgrade   - Upgrade full stack"
	@echo "  make uninstall - Remove full stack from AKS"
	@echo "  make status    - Show deployment status"
	@echo "  make show-env  - Show discovered Azure resources"
	@echo ""
	@echo "Per-service deployment:"
	@echo "  cd ask_api && make build && make deploy"
	@echo "  cd crawler && make build && make deploy"
	@echo ""
	@echo "Environment options:"
	@echo "  ENV_NAME=<name> # Target environment (default: $(ENV_NAME))"

# Local development
# Use 'pnpm link' in chat-app for local search-components development

frontend:
	@echo "Starting ask-api and chat-app..."
	@echo "Ask API: http://localhost:8000"
	@echo "Chat App: http://localhost:5173"
	@echo ""
	@echo "Press Ctrl+C to stop all services"
	@echo ""
	@trap 'echo "\nStopping services..."; docker-compose -f docker-compose.yml down; exit' INT TERM; \
	docker-compose -f docker-compose.yml up --build ask-api & \
	sleep 3; \
	cd chat-app && VITE_ASK_API_URL=http://localhost:8000 pnpm dev; \
	docker-compose -f docker-compose.yml down

fullstack:
	docker-compose -f docker-compose.yml up --build

down:
	docker-compose -f docker-compose.yml down

logs:
	docker-compose -f docker-compose.yml logs -f

install:
	$(call discover-azure-resources)
	$(call validate-azure-resources)
	$(call aks-login)
	helm install ask-api ./helm/ask-api \
		--set global.keyVault.name=$(KEYVAULT_NAME) \
		--set global.keyVault.tenantId=$(TENANT_ID) \
		--set global.containerRegistry.server=$(ACR_LOGIN_SERVER) \
		--set workloadIdentity.clientId=$(ASK_API_ID)
	helm install chat-app ./helm/chat-app \
		--set global.containerRegistry.server=$(ACR_LOGIN_SERVER)
	helm install crawler ./helm/crawler \
		--set global.keyVault.name=$(KEYVAULT_NAME) \
		--set global.keyVault.tenantId=$(TENANT_ID) \
		--set global.containerRegistry.server=$(ACR_LOGIN_SERVER) \
		--set workloadIdentity.clientId=$(CRAWLER_ID) \
		--set workloadIdentity.kedaIdentityId=$(KEDA_ID) \
		--set autoscaling.storageAccountName=$(STORAGE_NAME)

upgrade:
	$(call discover-azure-resources)
	$(call validate-azure-resources)
	$(call aks-login)
	helm upgrade ask-api ./helm/ask-api \
		--set global.keyVault.name=$(KEYVAULT_NAME) \
		--set global.keyVault.tenantId=$(TENANT_ID) \
		--set global.containerRegistry.server=$(ACR_LOGIN_SERVER) \
		--set workloadIdentity.clientId=$(ASK_API_ID) \
		--reuse-values
	helm upgrade chat-app ./helm/chat-app \
		--set global.containerRegistry.server=$(ACR_LOGIN_SERVER) \
		--reuse-values
	helm upgrade crawler ./helm/crawler \
		--set global.keyVault.name=$(KEYVAULT_NAME) \
		--set global.keyVault.tenantId=$(TENANT_ID) \
		--set global.containerRegistry.server=$(ACR_LOGIN_SERVER) \
		--set workloadIdentity.clientId=$(CRAWLER_ID) \
		--set workloadIdentity.kedaIdentityId=$(KEDA_ID) \
		--set autoscaling.storageAccountName=$(STORAGE_NAME) \
		--reuse-values

uninstall:
	$(call discover-azure-resources)
	$(call aks-login)
	-helm uninstall ask-api
	-helm uninstall chat-app
	-helm uninstall crawler

status:
	@echo "=== Helm Releases ==="
	@helm list -A | grep -E 'ask-api|chat-app|crawler|nlweb-gateway' || echo "No releases found"
	@echo ""
	@echo "=== Pods ==="
	@kubectl get pods -A | grep -E 'gateway|ask-api|chat-app|crawler' || echo "No pods found"
