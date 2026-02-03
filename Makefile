# NLWeb Helm Deployment
# Full stack deployment operations using environment-based resource discovery

include common.mk

.PHONY: help frontend fullstack down logs install upgrade uninstall status

help:
	@echo "NLWeb Development & Deployment"
	@echo ""
	@echo "Local Development:"
	@echo "  make frontend  - Start ask-api + chat-app (no crawler)"
	@echo "  make fullstack - Start all services (ask-api, chat-app, crawler)"
	@echo "  make down      - Stop all services"
	@echo "  make logs      - Tail logs from all services"
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
	@echo "  ENV_NAME=<name>   # Target environment (default: $(ENV_NAME))"
	@echo "  GIT_TOKEN=<token> # GitHub token for chat-app npm packages"
	@echo "  REFRESH=true|false # Use local search-components (default: true)"

# Local development with Docker Compose
# REFRESH=true (default): Use local search-components from peer directory
# REFRESH=false: Use published package from npm registry
REFRESH ?= true

ifeq ($(REFRESH),true)
COMPOSE_FILES = -f docker-compose.yml -f docker-compose.refresh.yml
FRONTEND_SERVICES = search-components ask-api chat-app
else
COMPOSE_FILES = -f docker-compose.yml
FRONTEND_SERVICES = ask-api chat-app
endif

frontend:
	docker-compose $(COMPOSE_FILES) up --build $(FRONTEND_SERVICES)

fullstack:
	docker-compose $(COMPOSE_FILES) up --build

down:
	docker-compose $(COMPOSE_FILES) down

logs:
	docker-compose $(COMPOSE_FILES) logs -f

install:
	$(call discover-azure-resources)
	$(call validate-azure-resources)
	$(call aks-login)
	helm install nlweb ./helm/nlweb \
		--set global.azure.tenantId=$(TENANT_ID) \
		--set global.keyVault.name=$(KEYVAULT_NAME) \
		--set global.keyVault.tenantId=$(TENANT_ID) \
		--set global.containerRegistry.server=$(ACR_LOGIN_SERVER) \
		--set ask-api.workloadIdentity.clientId=$(ASK_API_ID) \
		--set crawler.workloadIdentity.clientId=$(CRAWLER_ID) \
		--set crawler.workloadIdentity.kedaIdentityId=$(KEDA_ID) \
		--set crawler.autoscaling.storageAccountName=$(STORAGE_NAME)

upgrade:
	$(call discover-azure-resources)
	$(call validate-azure-resources)
	$(call aks-login)
	helm upgrade nlweb ./helm/nlweb \
		--set global.azure.tenantId=$(TENANT_ID) \
		--set global.keyVault.name=$(KEYVAULT_NAME) \
		--set global.keyVault.tenantId=$(TENANT_ID) \
		--set global.containerRegistry.server=$(ACR_LOGIN_SERVER) \
		--set ask-api.workloadIdentity.clientId=$(ASK_API_ID) \
		--set crawler.workloadIdentity.clientId=$(CRAWLER_ID) \
		--set crawler.workloadIdentity.kedaIdentityId=$(KEDA_ID) \
		--set crawler.autoscaling.storageAccountName=$(STORAGE_NAME) \
		--reuse-values

uninstall:
	$(call discover-azure-resources)
	$(call aks-login)
	helm uninstall nlweb

status:
	@echo "=== Helm Release ==="
	@helm list -A | grep nlweb || echo "No release found"
	@echo ""
	@echo "=== Pods ==="
	@kubectl get pods -A | grep -E 'gateway|ask-api|crawler' || echo "No pods found"
