import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En desarrollo, /api va al backend FastAPI (puerto 8740). En producción el
// propio backend sirve dist/, así que no hace falta proxy.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8740', changeOrigin: false } },
  },
})
