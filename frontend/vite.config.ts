/// <reference types="vitest/config" />
import { setDefaultResultOrder } from 'node:dns'
import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Canva OAuth의 loopback 주소(127.0.0.1)와 localhost가 같은 개발 서버를 사용한다.
setDefaultResultOrder('ipv4first')

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // 개발 중 /api 요청을 Spring(8080)으로 넘긴다. 배포 후에는 Nginx가 같은 일을 한다.
    // 8080을 다른 프로그램이 쓰면 API_PROXY_TARGET=http://localhost:8095 처럼 바꿔 띄운다.
    proxy: {
      '/api': process.env.API_PROXY_TARGET ?? 'http://localhost:8080',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
