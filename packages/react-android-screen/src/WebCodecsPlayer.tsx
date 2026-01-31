/**
 * WebCodecsPlayer - WebCodecs API を使った低遅延 H.264 プレイヤー
 * 
 * JMuxer/MSE の代わりに WebCodecs VideoDecoder を使用し、
 * Canvas に直接描画することで遅延を最小化する。
 */

import { useCallback, useEffect, useRef } from 'react'
import { useWebCodecsStream } from './useWebCodecsStream.js'
import type { StreamStatus } from './types.js'

export interface WebCodecsPlayerProps {
  wsUrl: string
  className?: string
  canvasClassName?: string
  canvasStyle?: React.CSSProperties
  debug?: boolean
  autoReconnect?: boolean
  reconnectInterval?: number
  onConnected?: () => void
  onDisconnected?: () => void
  onError?: (error: string) => void
}

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
      return 'ライブ (WebCodecs)'
    case 'connecting':
      return '接続中...'
    case 'error':
      return 'エラー'
    default:
      return '切断'
  }
}

/**
 * WebCodecs ベースの Android 画面ストリーミングプレイヤー
 */
export function WebCodecsPlayer({
  wsUrl,
  className = '',
  canvasClassName = '',
  canvasStyle,
  debug = false,
  autoReconnect = true,
  reconnectInterval = 3000,
  onConnected,
  onDisconnected,
  onError,
}: WebCodecsPlayerProps) {
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isUnmountedRef = useRef(false)
  const hasConnectedOnceRef = useRef(false)

  // connect を ref 経由で保持（依存配列の問題を回避）
  const connectRef = useRef<() => void>(() => {})

  const handleConnected = useCallback(() => {
    hasConnectedOnceRef.current = true
    onConnected?.()
  }, [onConnected])

  const handleDisconnected = useCallback(() => {
    onDisconnected?.()
    
    // 一度接続してから切断された場合のみ再接続
    if (autoReconnect && hasConnectedOnceRef.current && !isUnmountedRef.current) {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
      }
      reconnectTimerRef.current = setTimeout(() => {
        if (!isUnmountedRef.current) {
          if (debug) {
            console.log('[WebCodecs] Auto-reconnecting...')
          }
          connectRef.current()
        }
      }, reconnectInterval)
    }
  }, [autoReconnect, reconnectInterval, onDisconnected, debug])

  const { canvasRef, status, stats, connect, isSupported } = useWebCodecsStream({
    wsUrl,
    autoConnect: true,
    debug,
    onConnected: handleConnected,
    onDisconnected: handleDisconnected,
    onError,
  })

  // connect を ref に保存
  connectRef.current = connect

  // アンマウント時のクリーンアップ
  useEffect(() => {
    isUnmountedRef.current = false
    return () => {
      isUnmountedRef.current = true
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
      }
    }
  }, [])

  if (!isSupported) {
    return (
      <div className={`relative ${className}`}>
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          <strong>WebCodecs 非対応</strong>
          <p className="text-sm mt-1">
            このブラウザは WebCodecs API をサポートしていません。
            Chrome または Edge の最新版をお使いください。
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className={`relative ${className}`}>
      {/* ステータスバー */}
      <div className="absolute top-2 left-2 z-10 flex items-center gap-2 bg-black/50 text-white text-xs px-2 py-1 rounded">
        <span className={`w-2 h-2 rounded-full ${getStatusColor(status)}`} />
        <span>{getStatusLabel(status)}</span>
        <span className="text-gray-300">|</span>
        <span>{formatBytes(stats.bytes)}</span>
      </div>

      {/* Canvas */}
      <canvas
        ref={canvasRef}
        className={`w-full bg-black ${canvasClassName}`}
        style={{
          maxHeight: '70vh',
          objectFit: 'contain',
          ...canvasStyle,
        }}
      />

      {/* 切断時のオーバーレイ */}
      {status === 'disconnected' && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/70">
          <button
            onClick={connect}
            className="px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded"
          >
            再接続
          </button>
        </div>
      )}

      {/* エラー時のオーバーレイ */}
      {status === 'error' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/70 text-white">
          <span className="text-red-400 mb-2">接続エラー</span>
          <button
            onClick={connect}
            className="px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded"
          >
            再試行
          </button>
        </div>
      )}
    </div>
  )
}
