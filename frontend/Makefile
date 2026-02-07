# Frontend Makefile
# For AKS deployment, uses environment-based resource discovery
include ../common.mk

.DEFAULT_GOAL := help

.PHONY: help dev test lint format typecheck check build deploy down logs init_environment

# ==============================================================================
# Help
# ==============================================================================

help:
	@echo "Frontend"
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
	docker compose -f ../docker-compose.yml up --build chat-app

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
	@echo "No .env required for frontend."
