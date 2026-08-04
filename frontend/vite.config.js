import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const apiProxy = {
  target: 'http://localhost:8000',
  changeOrigin: true,
  rewrite: (path) => path.replace(/^\/api/, '')
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: 'jsdom',
    globals: true,
    css: true,
    passWithNoTests: true
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy: { '/api': apiProxy }
  },
  // 支持SPA路由的history模式
  preview: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy: { '/api': apiProxy }
  }
})
