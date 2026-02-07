# NLWeb Ask Agent

include common.mk

.DEFAULT_GOAL := help

.PHONY: help init_environment ask fullstack check build-all deploy-all

help:
	@echo "NLWeb Ask Agent"
	@echo ""
	@echo "Setup:"
	@echo "  make init_environment Generate .env files for ask-api and crawler"
	@echo ""
	@echo "Development:"
	@echo "  make ask              Start ask-api (Docker) + chat-app (native)"
	@echo "  make fullstack        Start all services in Docker"
	@echo "  make check            Run all checks across all modules"
	@echo ""
	@echo "Deployment:"
	@echo "  make build-all        Build all Docker images to ACR"
	@echo "  make deploy-all       Deploy all services to AKS"
	@echo ""
	@echo "Options:"
	@echo "  ENV_NAME=<name>       Azure environment (default: $(ENV_NAME))"

init_environment:
	cd ask_api && $(MAKE) init_environment
	cd crawler && $(MAKE) init_environment

ask:
	@echo "Starting ask-api and chat-app..."
	@echo "Ask API: http://localhost:8000"
	@echo "Chat App: http://localhost:5173"
	@echo ""
	@echo "Press Ctrl+C to stop all services"
	@echo ""
	@cd frontend && pnpm install && pnpm --filter @nlweb-ai/search-components build
	@trap 'echo "\nStopping services..."; docker-compose -f $(CURDIR)/docker-compose.yml down; exit' INT TERM; \
	docker-compose -f $(CURDIR)/docker-compose.yml up --build ask-api & \
	sleep 3; \
	cd frontend && VITE_ASK_API_URL=http://localhost:8000 pnpm --filter @nlweb-ai/chat-app dev; \
	docker-compose -f $(CURDIR)/docker-compose.yml down

fullstack:
	docker-compose -f docker-compose.yml up --build

check:
	cd ask_api && $(MAKE) check
	cd frontend && $(MAKE) check
	cd crawler && $(MAKE) check

build-all:
	cd ask_api && $(MAKE) build
	cd frontend && $(MAKE) build
	cd crawler && $(MAKE) build

deploy-all:
	cd ask_api && $(MAKE) deploy
	cd frontend && $(MAKE) deploy
	cd crawler && $(MAKE) deploy
