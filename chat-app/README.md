# Chat App

React frontend for NLWeb semantic search.

## Development

**Via Docker Compose (from repo root):**
```bash
make frontend
```
Open http://localhost:5173

**Native:**
```bash
pnpm install
pnpm dev
```
Requires ask-api running on port 8000.

## Build

```bash
pnpm build
pnpm start  # serves on port 3000
```

## Stack

- React 19 + TypeScript
- Vite (rolldown)
- Tailwind CSS 4
- Headless UI
- `@nlweb-ai/search-components` (GitHub Packages)
