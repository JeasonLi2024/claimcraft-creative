import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Vue 3 + Vite 配置：端口 5173，/api 代理到 Django 后端
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
