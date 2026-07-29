import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// dev 环境将 /api 与 /videos 代理到 FastAPI 后端
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/videos': 'http://localhost:8000',
    },
  },
})
