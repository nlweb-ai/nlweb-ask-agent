# Ask API

REST API for semantic search over crawled content.

## Endpoints

- `GET/POST /ask` - Query endpoint (`query`, `site`, `num_results`, `streaming`)
- `GET /health` - Health check
- `POST /mcp` - MCP JSON-RPC
- `POST /a2a` - A2A JSON-RPC

## Package Structure

```
packages/
├── core/         # Framework, config, orchestration
├── network/      # Protocol adapters (HTTP, MCP, A2A)
└── providers/    # Pluggable provider implementations
```

Providers are configured via `config.yaml` with `import_path` and `class_name`.

## Commands

Run `make help` for the full list. Key targets:

```
make dev     # Run locally via Docker Compose (port 8000)
make test    # Run pytest
make build   # Build image to ACR
make deploy  # Deploy to AKS via Helm
```
