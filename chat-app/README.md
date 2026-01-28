# Chat App

React frontend for NLWeb semantic search.

## Development

**Via Docker Compose (from repo root):**
```bash
export GIT_TOKEN=<github-classic-pat-with-read:packages>
make frontend
```
Open http://localhost:5173

**Native:**
```bash
export GIT_TOKEN=<your-token>
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
