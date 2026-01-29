import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import fs from 'fs'
import path from 'path'

// API target: use VITE_ASK_API_URL env var for Docker, fallback to localhost for native dev
const apiTarget = process.env.VITE_ASK_API_URL || 'http://localhost:8000'

// Plugin to watch search-components dist using polling (for Docker cross-container mounts)
function searchComponentsWatcher() {
  const distPath = '/app/node_modules/@nlweb-ai/search-components/dist'
  let lastMtime = 0
  let pollInterval: ReturnType<typeof setInterval> | null = null
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  return {
    name: 'search-components-watcher',
    configureServer(server: any) {
      console.log('[search-components] Starting poll watcher for:', distPath)

      // Poll for changes since Docker events don't propagate between containers
      pollInterval = setInterval(() => {
        try {
          const indexPath = path.join(distPath, 'index.js')
          const stat = fs.statSync(indexPath)
          const mtime = stat.mtimeMs

          if (lastMtime > 0 && mtime > lastMtime) {
            console.log('[search-components] Change detected via polling')
            if (debounceTimer) clearTimeout(debounceTimer)
            debounceTimer = setTimeout(() => {
              console.log('[search-components] Restarting server to re-bundle...')
              server.restart()
            }, 500)
          }
          lastMtime = mtime
        } catch (e) {
          // File might not exist yet, ignore
        }
      }, 1000)

      // Cleanup on server close
      server.httpServer?.on('close', () => {
        if (pollInterval) clearInterval(pollInterval)
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), searchComponentsWatcher()],
  optimizeDeps: {
    // Force re-bundle on every server start (needed for mounted search-components)
    force: true,
    // Force pre-bundle CJS packages
    include: [
      'react',
      'react-dom',
      'react/jsx-runtime',
      'use-sync-external-store',
      'use-sync-external-store/with-selector',
    ],
  },
  resolve: {
    // Ensure single copy of shared packages
    dedupe: ['react', 'react-dom', 'use-sync-external-store'],
  },
  server: {
    host: '0.0.0.0', // Allow external connections (needed for Docker)
    port: 5173,
    // Allow serving files from the mounted search-components directory
    fs: {
      allow: ['..'],
    },
    watch: {
      // Use polling for Docker volume mounts (more reliable for cross-container changes)
      usePolling: true,
      interval: 500,
      // Override default ignore to watch mounted search-components
      ignored: (path: string) => {
        // Always watch search-components
        if (path.includes('@nlweb-ai/search-components')) {
          return false
        }
        // Ignore other node_modules and .git
        if (path.includes('node_modules') || path.includes('.git')) {
          return true
        }
        return false
      },
    },
    proxy: {
      '/ask': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/health': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/mcp': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/a2a': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
