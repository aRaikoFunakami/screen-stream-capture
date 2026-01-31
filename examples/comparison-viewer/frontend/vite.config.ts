import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  // ローカル開発時は localhost、Docker 内では backend
  const backendHost = env.VITE_BACKEND_HOST ?? 'localhost'
  const backendPort = env.VITE_BACKEND_PORT ?? '8000'
  const backendHttp = env.VITE_BACKEND_HTTP ?? `http://${backendHost}:${backendPort}`
  const backendWs = env.VITE_BACKEND_WS ?? `ws://${backendHost}:${backendPort}`

  // Docker 内かローカルかで react-android-screen のパスを切り替え
  const dockerPkgPath = '/app/packages/react-android-screen/src'
  const localPkgPath = path.resolve(__dirname, '../../../packages/react-android-screen/src')
  const pkgPath = fs.existsSync(dockerPkgPath) ? dockerPkgPath : localPkgPath

  return {
    plugins: [react()],
    resolve: {
      alias: {
        'react-android-screen': pkgPath,
      },
    },
    server: {
      host: true, // 外部からのアクセスを許可
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
