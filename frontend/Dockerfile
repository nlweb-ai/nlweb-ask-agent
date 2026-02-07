# Build stage
FROM node:22-alpine AS builder

WORKDIR /workspace

# Install pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy workspace config + package manifests (for layer caching)
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY chat-app/package.json chat-app/
COPY search-components/package.json search-components/

# Install dependencies
RUN pnpm install --frozen-lockfile

# Copy sources
COPY search-components/ search-components/
COPY chat-app/ chat-app/

# Build search-components (workspace dep), then chat-app
RUN pnpm --filter @nlweb-ai/search-components build
RUN pnpm --filter @nlweb-ai/chat-app build

# Production stage
FROM node:22-alpine

WORKDIR /app

# Install serve globally
RUN npm install -g serve@14

# Copy built assets
COPY --from=builder /workspace/chat-app/dist ./dist

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q --spider http://localhost:3000/ || exit 1

# Run serve (-s for single page app mode, -l for listen port)
CMD ["serve", "dist", "-s", "-l", "3000"]
