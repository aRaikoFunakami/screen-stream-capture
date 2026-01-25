import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api/ws': {
        target: 'ws://backend:8000',
        changeOrigin: true,
        ws: true,
        configure: (proxy) => {
          proxy.on('proxyReqWs', (_proxyReq, req) => {
            console.log('[vite ws proxyReqWs]', req.url)
          })
          proxy.on('open', () => console.log('[vite ws open]'))
          proxy.on('close', () => console.log('[vite ws close]'))
          proxy.on('error', (err, req) => {
            console.log('[vite ws error]', err.message, req?.url)
          })
        },
      },
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
})
