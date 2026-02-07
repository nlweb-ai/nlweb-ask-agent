# Frontend

pnpm workspace containing the web UI and shared components.

## Packages

- **chat-app** - React application for the search interface
- **search-components** - Shared React component library

## Commands

Run `make help` for the full list. Key targets:

```
make init_environment  # Generate .env with API URL from active K8s cluster
make dev               # Run Vite dev server (port 5173, proxies to API from .env)
make check             # Lint, format, typecheck
make build             # Build image to ACR
make deploy            # Deploy to AKS via Helm
```

`make dev` reads `VITE_ASK_API_URL` from `.env` to configure the Vite proxy.
Without a `.env`, it falls back to `http://localhost:8000`.
