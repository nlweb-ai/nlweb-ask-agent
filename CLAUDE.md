# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NLWeb Ask Agent is a distributed question-answering system with semantic search over crawled web content. It consists of three main components:

- **Ask API** (`/ask_api`): REST API for semantic search queries with MCP/A2A protocol support
- **Chat App** (`/chat-app`): React frontend for the search interface
- **Crawler** (`/crawler`): Web crawler for schema.org structured data extraction

## Local Development

### Docker Compose (recommended)

```bash
# First time setup - generate .env files
cd ask_api && make init_environment && cd ..
cd crawler && make init_environment && cd ..

# Start frontend only (ask-api + chat-app)
export GIT_TOKEN=<github-classic-pat-with-read:packages>
make frontend

# Start full stack (includes crawler)
make fullstack

# Stop all services
make down

# Tail logs
make logs
```

Services:
- chat-app: http://localhost:5173 (with HMR)
- ask-api: http://localhost:8000
- crawler: http://localhost:5001

### Native Development (single service)

```bash
# Ask API
cd ask_api && make dev

# Chat App
cd chat-app && pnpm dev

# Crawler
cd crawler && make dev-master  # + make dev-worker in another terminal
```

## AKS Deployment

```bash
make install   # Initial install
make upgrade   # Upgrade existing
make status    # Check deployment
```

Per-service:
```bash
cd ask_api && make build && make deploy
cd crawler && make build && make deploy
```

## Architecture

### Config-Driven Provider System

The Ask API uses a pluggable provider architecture driven by `ask_api/config.yaml`. Provider categories: `high-llm-model`, `low-llm-model`, `embedding`, `scoring-llm-model`, `retrieval`, `object_storage`, `site_config`

### Package Structure (Ask API)

- `nlweb-core` (`packages/core`): Framework, config, orchestration
- `nlweb-network` (`packages/network`): Protocol adapters (HTTP/MCP/A2A)
- Provider packages in `packages/providers/`

### Multi-Protocol Support

Ask API exposes: `/ask`, `/mcp`, `/mcp-sse`, `/a2a`, `/a2a-sse`, `/health`

### Crawler Architecture

Master/worker pattern with file-based queue. Flow: Parse schema.org sitemaps → queue JSON files → embed → upload to Azure AI Search

## Testing

```bash
cd ask_api && make test
cd crawler && make test
```

## Adding New Providers

1. Create package in `ask_api/packages/providers/<provider>/`
2. Implement required interface
3. Add workspace entry to `ask_api/pyproject.toml`
4. Update `ask_api/config.yaml`
