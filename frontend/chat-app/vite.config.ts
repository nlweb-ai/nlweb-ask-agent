import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const apiTarget = process.env.VITE_ASK_API_URL

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  optimizeDeps: {
    // Force pre-bundle CJS packages
    include: [
      'react',
      'react-dom',
      'react/jsx-runtime',
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
