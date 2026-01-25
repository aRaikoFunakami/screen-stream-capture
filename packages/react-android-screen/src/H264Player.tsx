/**
 * H264Player - H.264 ストリーミングプレイヤーコンポーネント
 */

import { useRef, useEffect } from 'react'
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
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isUnmountedRef = useRef(false)
  const hasConnectedOnceRef = useRef(false)
  const connectRef = useRef<() => void>(() => {})

  const { videoRef, status, stats, connect, disconnect } = useAndroidStream({
    wsUrl,
    autoConnect: true,
    fps,
    onConnected: () => {
      hasConnectedOnceRef.current = true
      onConnected?.()
    },
    onDisconnected,
    onError,
  })

  // connect を ref に保存して依存配列の問題を回避
  connectRef.current = connect

  // 自動再接続の処理（一度接続した後のみ）
  useEffect(() => {
    if (status === 'disconnected' && autoReconnect && hasConnectedOnceRef.current && !isUnmountedRef.current) {
      // 既存のタイマーをクリア
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
      }
      // 再接続をスケジュール
      reconnectTimerRef.current = setTimeout(() => {
        if (!isUnmountedRef.current) {
          console.log('Auto-reconnecting...')
          connectRef.current()
        }
      }, reconnectInterval)
    }

    return () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
      }
    }
  }, [status, autoReconnect, reconnectInterval])

  // アンマウント時のクリーンアップ
  useEffect(() => {
    isUnmountedRef.current = false
    return () => {
      isUnmountedRef.current = true
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
      }
      disconnect()
    }
  }, [disconnect])

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
