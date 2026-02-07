# NLWeb Ask Agent

include common.mk

.DEFAULT_GOAL := help

.PHONY: help init_environment ask fullstack down logs check

help:
	@echo "NLWeb Ask Agent"
	@echo ""
	@echo "Setup:"
	@echo "  make init_environment Generate .env files for ask-api and crawler"
	@echo ""
	@echo "Development:"
	@echo "  make ask              Start ask-api (Docker) + chat-app (native)"
	@echo "  make fullstack        Start all services in Docker"
	@echo "  make down             Stop Docker services"
	@echo "  make logs             Tail logs from Docker services"
	@echo "  make check            Run all checks across all modules"
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

down:
	docker-compose -f docker-compose.yml down

logs:
	docker-compose -f docker-compose.yml logs -f

check:
	cd ask_api && $(MAKE) check
	cd frontend && $(MAKE) check
	cd crawler && $(MAKE) check
