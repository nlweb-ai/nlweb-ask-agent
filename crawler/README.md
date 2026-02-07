# Crawler

Distributed web crawler for schema.org structured data.

## Architecture

Master/worker pattern running as separate pods in Kubernetes:
- **Master**: Flask API + job scheduler
- **Worker**: Queue processor (embedding + upload to Azure AI Search)

Flow: Parse schema.org sitemaps → queue JSON files → embed → upload

## Endpoints

- `GET /` - Web UI
- `GET /api/status` - System status
- `POST /api/sites` - Add site to crawl
- `GET /api/queue/status` - Queue statistics

## Commands

Run `make help` for the full list. Key targets:

```
make dev     # Run master + worker via Docker Compose
make test    # Run pytest
make build   # Build image to ACR
make deploy  # Deploy to AKS via Helm
```
