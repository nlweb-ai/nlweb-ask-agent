# Chat App

React frontend for NLWeb semantic search.

## Development

**Via Docker Compose (from repo root):**
```bash
make ask
```
Open http://localhost:5173

**Native (from frontend/ directory):**
```bash
pnpm install
pnpm --filter @nlweb-ai/chat-app dev
```
Requires ask-api running on port 8000.

## Build

```bash
# From frontend/ directory
pnpm --filter @nlweb-ai/chat-app build
pnpm --filter @nlweb-ai/chat-app start  # serves on port 3000
```

## Stack

- React 19 + TypeScript
- Vite (rolldown)
- Tailwind CSS 4
- Headless UI
- `@nlweb-ai/search-components` (workspace package)
