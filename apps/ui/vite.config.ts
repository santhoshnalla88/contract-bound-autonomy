import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev, proxy API + health + SSE to the FastAPI backend on :8000 so the
// browser talks same-origin (no CORS) and EventSource streaming works.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/health': { target: 'http://localhost:8000', changeOrigin: true },
      '/ready': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
