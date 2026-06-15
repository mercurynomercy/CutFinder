import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  server: {
    port: 5080,
    // Proxy API + SSE calls to the FastAPI backend (see scripts/dev.sh).
    proxy: {
      '/api': { target: 'http://localhost:5081', changeOrigin: true },
    },
  },
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
