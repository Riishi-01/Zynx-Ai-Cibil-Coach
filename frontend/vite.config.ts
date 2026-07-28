import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // The FastAPI backend runs on :8000 in dev. Proxying /api avoids CORS
      // entirely and keeps fetch('/api/...') calls identical between dev and
      // the production build, where FastAPI serves the built assets directly.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
