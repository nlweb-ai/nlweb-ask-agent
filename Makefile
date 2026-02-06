# NLWeb Ask Agent

include common.mk

.PHONY: help init_environment ask fullstack down logs

help:
	@echo "NLWeb Ask Agent"
	@echo ""
	@echo "Setup:"
	@echo "  make init_environment - Generate .env files for ask-api and crawler"
	@echo ""
	@echo "Development:"
	@echo "  make ask       - Start ask-api (Docker) + chat-app (native)"
	@echo "  make fullstack - Start all services in Docker"
	@echo "  make down      - Stop Docker services"
	@echo "  make logs      - Tail logs from Docker services"
	@echo ""
	@echo "Options:"
	@echo "  ENV_NAME=<name> - Azure environment (default: $(ENV_NAME))"

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
	@trap 'echo "\nStopping services..."; docker-compose -f docker-compose.yml down; exit' INT TERM; \
	docker-compose -f docker-compose.yml up --build ask-api & \
	sleep 3; \
	cd frontend && VITE_ASK_API_URL=http://localhost:8000 pnpm --filter @nlweb-ai/chat-app dev; \
	docker-compose -f docker-compose.yml down

fullstack:
	docker-compose -f docker-compose.yml up --build

down:
	docker-compose -f docker-compose.yml down

logs:
	docker-compose -f docker-compose.yml logs -f
