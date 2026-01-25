/**
 * H264Player - H.264 ストリーミングプレイヤーコンポーネント
 */

import { useAndroidStream } from './useAndroidStream'
import type { H264PlayerProps, StreamStatus } from './types'

/**
 * バイト数を人間が読める形式にフォーマット
 */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

/**
 * ステータスに応じたインジケーターの色
 */
function getStatusColor(status: StreamStatus): string {
  switch (status) {
    case 'connected':
      return 'bg-green-500'
    case 'connecting':
      return 'bg-yellow-500 animate-pulse'
    case 'error':
      return 'bg-red-500'
    default:
      return 'bg-gray-500'
  }
}

/**
 * ステータスに応じたラベル
 */
function getStatusLabel(status: StreamStatus): string {
  switch (status) {
    case 'connected':
      return 'ライブ'
    case 'connecting':
      return '接続中...'
    case 'error':
      return 'エラー'
    default:
      return '切断'
  }
}

/**
 * Android 画面ストリーミングプレイヤー
 * 
 * @example
 * ```tsx
 * <H264Player
 *   wsUrl="/api/ws/stream/emulator-5554"
 *   className="w-full max-w-2xl"
 *   onConnected={() => console.log('connected')}
 * />
 * ```
 */
export function H264Player({
  wsUrl,
  className = '',
  onConnected,
  onDisconnected,
  onError,
  fps = 30,
  autoReconnect = true,
  reconnectInterval = 3000,
}: H264PlayerProps) {
  const { videoRef, status, stats, connect } = useAndroidStream({
    wsUrl,
    autoConnect: true,
    fps,
    onConnected,
    onDisconnected: () => {
      onDisconnected?.()
      // 自動再接続
      if (autoReconnect) {
        setTimeout(connect, reconnectInterval)
      }
    },
    onError,
  })

  return (
    <div className={`relative bg-black rounded-lg overflow-hidden ${className}`}>
      <video
        ref={videoRef}
        autoPlay
        muted
        playsInline
        className="w-full h-auto"
        style={{ maxHeight: '70vh' }}
      />
      
      {/* ステータスオーバーレイ */}
      <div className="absolute top-2 left-2 flex items-center gap-2 bg-black/50 text-white px-2 py-1 rounded text-sm">
        <span className={`w-2 h-2 rounded-full ${getStatusColor(status)}`} />
        <span>{getStatusLabel(status)}</span>
      </div>

      {/* 統計情報 */}
      {status === 'connected' && (
        <div className="absolute bottom-2 left-2 bg-black/50 text-white px-2 py-1 rounded text-xs">
          {formatBytes(stats.bytes)} / {stats.chunks} chunks
        </div>
      )}

      {/* 再接続ボタン */}
      {(status === 'disconnected' || status === 'error') && !autoReconnect && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/70">
          <button
            onClick={connect}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors"
          >
            再接続
          </button>
        </div>
      )}
    </div>
  )
}
