# Frontend Makefile
# For AKS deployment, uses environment-based resource discovery
include ../common.mk

# Load .env if present (sets VITE_ASK_API_URL for dev server)
-include .env
export VITE_ASK_API_URL

.DEFAULT_GOAL := help

.PHONY: help dev test lint format typecheck check build deploy down logs init_environment

# ==============================================================================
# Help
# ==============================================================================

help:
	@echo "Frontend"
	@echo ""
	@echo "Development:"
	@echo "  make dev              Run Vite dev server (reads VITE_ASK_API_URL from .env)"
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
	@echo "  make init_environment Generate .env with API URL from active K8s cluster"
	@echo ""
	@echo "Options:"
	@echo "  ENV_NAME=<name>       Azure environment (default: $(ENV_NAME))"

# ==============================================================================
# Development
# ==============================================================================

dev:
	pnpm install
	pnpm --filter @nlweb-ai/search-components build
	pnpm --filter @nlweb-ai/chat-app dev

# ==============================================================================
# Code Quality
# ==============================================================================

test:
	@echo "No tests configured."

lint:
	pnpm -r lint

format:
	pnpm -r format

typecheck:
	pnpm -r typecheck

check: lint format typecheck test

# ==============================================================================
# Deployment
# ==============================================================================

build:
	$(call discover-azure-resources)
	$(call validate-azure-resources)
	az acr build \
		--registry $(ACR_LOGIN_SERVER) \
		--image chat-app:latest \
		.

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

down:
	$(call discover-azure-resources)
	$(call aks-login)
	helm uninstall chat-app

logs:
	kubectl logs -n chat-app -l app=chat-app -f

# ==============================================================================
# Setup
# ==============================================================================

init_environment:
	$(call discover-azure-resources)
	$(call aks-login)
	@HOSTNAME=$$(kubectl get certificate nlweb-tls-cert -n gateway -o jsonpath='{.spec.dnsNames[0]}' 2>/dev/null); \
	if [ -z "$$HOSTNAME" ]; then \
		echo "No TLS certificate found. Falling back to gateway address..."; \
		HOSTNAME=$$(kubectl get gateway nlweb-gateway -n gateway -o jsonpath='{.status.addresses[0].value}' 2>/dev/null); \
	fi; \
	if [ -z "$$HOSTNAME" ]; then \
		echo "Error: Could not discover hostname from cluster."; \
		exit 1; \
	fi; \
	echo "VITE_ASK_API_URL=https://$$HOSTNAME" > .env; \
	echo ".env file created: VITE_ASK_API_URL=https://$$HOSTNAME"
