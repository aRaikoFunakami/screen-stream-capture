import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  // Docker Compose 内では `backend:8000` が解決できるが、ホストで `npm run dev` する場合は解決できない。
  // 必要に応じて `.env.local` などで以下を上書きする:
  // - VITE_BACKEND_HOST=127.0.0.1
  // - VITE_BACKEND_PORT=8000
  // もしくは完全指定:
  // - VITE_BACKEND_HTTP=http://127.0.0.1:8000
  // - VITE_BACKEND_WS=ws://127.0.0.1:8000
  const env = loadEnv(mode, process.cwd(), '')

  const backendHost = env.VITE_BACKEND_HOST ?? 'backend'
  const backendPort = env.VITE_BACKEND_PORT ?? '8000'
  const backendHttp = env.VITE_BACKEND_HTTP ?? `http://${backendHost}:${backendPort}`
  const backendWs = env.VITE_BACKEND_WS ?? `ws://${backendHost}:${backendPort}`

  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api/ws': {
          target: backendWs,
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
          target: backendHttp,
          changeOrigin: true,
        },
      },
    },
  }
})
