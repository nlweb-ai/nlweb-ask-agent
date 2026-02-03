import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// API target: use VITE_ASK_API_URL env var or fallback to localhost
const apiTarget = process.env.VITE_ASK_API_URL || 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  optimizeDeps: {
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
    host: '0.0.0.0',
    port: 5173,
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
