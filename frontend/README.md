# Frontend

pnpm workspace containing the web UI and shared components.

## Packages

- **chat-app** - React application for the search interface
- **search-components** - Shared React component library

## Commands

Run `make help` for the full list. Key targets:

```
make dev     # Run via Docker Compose (port 5173)
make check   # Lint, format, typecheck
make build   # Build image to ACR
make deploy  # Deploy to AKS via Helm
```
