import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendUrl = env.VITE_API_BASE || 'http://localhost:8000'

  return {
    plugins: [react(), tailwindcss()],
    server: {
      // Local dev: proxy /api and /uploads to the local backend
      proxy: {
        '/api': { target: 'http://localhost:8000', changeOrigin: true },
        '/uploads': { target: 'http://localhost:8000', changeOrigin: true },
      },
    },
    define: {
      // Exposes resolved backend URL for optional compile-time usage.
      __BACKEND_URL__: JSON.stringify(backendUrl),
    },
  }
})
