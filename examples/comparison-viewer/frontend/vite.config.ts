import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  const backendHost = env.VITE_BACKEND_HOST ?? 'backend'
  const backendPort = env.VITE_BACKEND_PORT ?? '8000'
  const backendHttp = env.VITE_BACKEND_HTTP ?? `http://${backendHost}:${backendPort}`
  const backendWs = env.VITE_BACKEND_WS ?? `ws://${backendHost}:${backendPort}`

  return {
    plugins: [react()],
    server: {
      port: 5174, // simple-viewer と別ポート
      proxy: {
        '/api/ws': {
          target: backendWs,
          changeOrigin: true,
          ws: true,
        },
        '/api': {
          target: backendHttp,
          changeOrigin: true,
        },
      },
    },
  }
})
