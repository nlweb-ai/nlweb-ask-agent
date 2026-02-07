# Deployment Makefile
# Deploys and manages Azure infrastructure and Kubernetes resources
include ../common.mk

.DEFAULT_GOAL := help

.PHONY: help login validate deploy destroy setup-k8s \
        request-certificate check-certificate enable-tls load-synthetic deploy-dashboards

LOCATION ?= centralus
CERT_MANAGER_EMAIL ?= admin@nlweb.ai

# ==============================================================================
# Help
# ==============================================================================

help:
	@echo "Deployment"
	@echo ""
	@echo "Infrastructure:"
	@echo "  make login              Login to Azure CLI"
	@echo "  make validate           Validate Bicep templates"
	@echo "  make deploy             Deploy Azure infrastructure (Bicep)"
	@echo "  make destroy            Delete all deployed resources"
	@echo ""
	@echo "Kubernetes:"
	@echo "  make setup-k8s          Setup K8s (cert-manager, KEDA, ALB, Gateway)"
	@echo ""
	@echo "TLS:"
	@echo "  make request-certificate  Request TLS certificate from Let's Encrypt"
	@echo "  make check-certificate    Check certificate and secret status"
	@echo "  make enable-tls           Enable TLS on the Gateway"
	@echo ""
	@echo "Data:"
	@echo "  make load-synthetic     Load synthetic schema data into crawler"
	@echo "  make deploy-dashboards  Deploy Grafana dashboards"
	@echo ""
	@echo "Debug:"
	@echo "  make show-env           Show discovered Azure resources"
	@echo ""
	@echo "Required environment variables:"
	@echo "  PI_LABS_ENDPOINT        PI Labs AzureML endpoint URL"
	@echo "  PI_LABS_KEY             PI Labs API key"
	@echo ""
	@echo "Options:"
	@echo "  ENV_NAME=<name>         Azure environment (default: $(ENV_NAME))"
	@echo "  LOCATION=<region>       Azure region (default: $(LOCATION))"

# ==============================================================================
# Infrastructure
# ==============================================================================

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
	@if [ -n "$(APP_PRINCIPAL_ID)" ]; then echo "  App Principal: $(APP_PRINCIPAL_ID)"; fi
	@echo ""
	az deployment sub create \
		--name "nlweb-$(ENV_NAME)-$$(date +%Y%m%d%H%M%S)" \
		--location $(LOCATION) \
		--template-file infra/main.bicep \
		--parameters environmentName=$(ENV_NAME) \
		--parameters location=$(LOCATION) \
		--parameters principalId=$$(az ad signed-in-user show --query id -o tsv 2>/dev/null || echo "") \
		$(if $(APP_PRINCIPAL_ID),--parameters appPrincipalId=$(APP_PRINCIPAL_ID),) \
		--parameters piLabsEndpoint="$$PI_LABS_ENDPOINT" \
		--parameters piLabsKey="$$PI_LABS_KEY" \
		--output table
	@echo ""
	@echo "=== Azure Infrastructure Deployed ==="
	@echo ""
	@echo "Next steps:"
	@echo "  make setup-k8s ENV_NAME=$(ENV_NAME)"
	@echo "  make build-all ENV_NAME=$(ENV_NAME)     (from repo root)"
	@echo "  make deploy-all ENV_NAME=$(ENV_NAME)    (from repo root)"
	@echo ""

destroy:
	@echo "This will delete the resource group '$(RG_NAME)' and ALL resources in it."
	@read -p "Are you sure? (yes/no): " confirm && [ "$$confirm" = "yes" ] || (echo "Aborted." && exit 1)
	az group delete --name $(RG_NAME) --yes --no-wait
	@echo "Resource group deletion initiated. This may take several minutes."

# ==============================================================================
# Kubernetes
# ==============================================================================

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

# ==============================================================================
# TLS
# ==============================================================================

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

enable-tls:
	@echo "Enabling TLS on Gateway..."
	@kubectl get secret nlweb-tls-secret -n gateway >/dev/null 2>&1 || \
		(echo "Error: TLS secret 'nlweb-tls-secret' not found. Run 'make request-certificate' first and wait for it to be ready." && exit 1)
	@echo "TLS secret found. Upgrading Gateway..."
	$(MAKE) setup-k8s

# ==============================================================================
# Data
# ==============================================================================

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

deploy-dashboards:
	@echo "Deploying Grafana dashboards..."
	@echo "  Environment: $(ENV_NAME)"
	@echo ""
	$(call discover-azure-resources)
	GRAFANA_NAME=$$(az grafana list -g $(RG_NAME) --query "[0].name" -o tsv) && \
	if [ -z "$$GRAFANA_NAME" ]; then \
		echo "Error: No Grafana instance found in resource group $(RG_NAME)"; \
		exit 1; \
	fi && \
	echo "  Grafana: $$GRAFANA_NAME" && \
	GRAFANA_NAME=$$GRAFANA_NAME AZURE_RESOURCE_GROUP=$(RG_NAME) ./scripts/deploy_dashboards.sh
