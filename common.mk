# common.mk - Shared Makefile variables and functions for NLWeb
# Include this at the top of Makefiles: include common.mk (or ../common.mk)

# Default environment name (override with: make <target> ENV_NAME=myenv)
ENV_NAME ?= nlweb-yoast-centralus

# Derived names
RG_NAME = rg-$(ENV_NAME)

# Azure resource discovery functions
# These use $(eval) to set variables from Azure CLI queries
# Call with: $(call discover-azure-resources)

define discover-azure-resources
$(eval ACR_NAME := $(shell az acr list -g $(RG_NAME) --query "[0].name" -o tsv 2>/dev/null))
$(eval ACR_LOGIN_SERVER := $(shell az acr show -n $(ACR_NAME) --query loginServer -o tsv 2>/dev/null))
$(eval AKS_NAME := $(shell az aks list -g $(RG_NAME) --query "[0].name" -o tsv 2>/dev/null))
$(eval KEYVAULT_NAME := $(shell az keyvault list -g $(RG_NAME) --query "[?!contains(name, 'aif')].name | [0]" -o tsv 2>/dev/null))
$(eval STORAGE_NAME := $(shell az storage account list -g $(RG_NAME) --query "[0].name" -o tsv 2>/dev/null))
$(eval ASK_API_ID := $(shell az identity list -g $(RG_NAME) --query "[?contains(name, 'askapi')].clientId" -o tsv 2>/dev/null))
$(eval CRAWLER_ID := $(shell az identity list -g $(RG_NAME) --query "[?contains(name, 'crawler')].clientId" -o tsv 2>/dev/null))
$(eval KEDA_ID := $(shell az identity list -g $(RG_NAME) --query "[?contains(name, 'keda')].clientId" -o tsv 2>/dev/null))
$(eval ALB_CONTROLLER_ID := $(shell az identity list -g $(RG_NAME) --query "[?contains(name, 'alb')].clientId" -o tsv 2>/dev/null))
$(eval ALB_SUBNET := $(shell az network vnet subnet show -g $(RG_NAME) --vnet-name $$(az network vnet list -g $(RG_NAME) --query "[0].name" -o tsv) -n snet-alb --query id -o tsv 2>/dev/null))
$(eval TENANT_ID := $(shell az account show --query tenantId -o tsv 2>/dev/null))
endef

# Validate that required resources were discovered
define validate-azure-resources
@if [ -z "$(ACR_NAME)" ]; then \
	echo "Error: Could not find ACR in resource group $(RG_NAME)"; \
	echo "Make sure infrastructure is deployed and you're logged in to Azure."; \
	exit 1; \
fi
@if [ -z "$(AKS_NAME)" ]; then \
	echo "Error: Could not find AKS in resource group $(RG_NAME)"; \
	echo "Make sure infrastructure is deployed."; \
	exit 1; \
fi
endef

# Login to AKS cluster
define aks-login
az aks get-credentials --resource-group $(RG_NAME) --name $(AKS_NAME) --overwrite-existing
endef

# Show discovered environment (for debugging)
.PHONY: show-env
show-env:
	$(call discover-azure-resources)
	@echo "Environment: $(ENV_NAME)"
	@echo "Resource Group: $(RG_NAME)"
	@echo ""
	@echo "Discovered Resources:"
	@echo "  ACR_NAME: $(ACR_NAME)"
	@echo "  ACR_LOGIN_SERVER: $(ACR_LOGIN_SERVER)"
	@echo "  AKS_NAME: $(AKS_NAME)"
	@echo "  KEYVAULT_NAME: $(KEYVAULT_NAME)"
	@echo "  STORAGE_NAME: $(STORAGE_NAME)"
	@echo "  ALB_SUBNET: $(ALB_SUBNET)"
	@echo ""
	@echo "Workload Identity Client IDs:"
	@echo "  ASK_API_ID: $(ASK_API_ID)"
	@echo "  CRAWLER_ID: $(CRAWLER_ID)"
	@echo "  KEDA_ID: $(KEDA_ID)"
	@echo "  ALB_CONTROLLER_ID: $(ALB_CONTROLLER_ID)"
	@echo ""
	@echo "Tenant:"
	@echo "  TENANT_ID: $(TENANT_ID)"
