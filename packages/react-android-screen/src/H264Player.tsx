/**
 * H264Player - H.264 ストリーミングプレイヤーコンポーネント
 */

import { useRef, useEffect, useState, useCallback } from 'react'
import { useAndroidStream } from './useAndroidStream.js'
import type { H264PlayerFit, H264PlayerProps, StreamStatus } from './types.js'

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
  videoClassName = '',
  videoStyle,
  fit = 'contain',
  maxHeight = '70vh',
  onConnected,
  onDisconnected,
  onError,
  fps = 30,
  liveSync = true,
  maxLatencyMs = 1500,
  targetLatencyMs = 300,
  stallRecovery = true,
  stallTimeoutMs = 2000,
  maxRecoveries = 3,
  recoveryCooldownMs = 1000,
  debug = false,
  autoReconnect = true,
  reconnectInterval = 3000,
}: H264PlayerProps) {
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isUnmountedRef = useRef(false)
  const hasConnectedOnceRef = useRef(false)
  const connectRef = useRef<() => void>(() => {})
  const [aspectRatio, setAspectRatio] = useState<string | null>(null)

  const updateAspectRatioFromVideo = useCallback(() => {
    const video = videoRef.current
    if (!video) return

    const { videoWidth, videoHeight } = video
    if (videoWidth > 0 && videoHeight > 0) {
      const ratio = `${videoWidth} / ${videoHeight}`
      // video の intrinsic size 変更に追従できるよう、video と wrapper 両方へ反映
      video.style.aspectRatio = ratio
      setAspectRatio(ratio)
    }
  }, [])

  const { videoRef, status, stats, connect, disconnect } = useAndroidStream({
    wsUrl,
    autoConnect: true,
    fps,
    liveSync,
    maxLatencyMs,
    targetLatencyMs,
    stallRecovery,
    stallTimeoutMs,
    maxRecoveries,
    recoveryCooldownMs,
    debug,
    onConnected: () => {
      hasConnectedOnceRef.current = true
      onConnected?.()
    },
    onDisconnected,
    onError,
    // JMuxer のリセット完了後に呼ばれるので、ここでレイアウト更新を促す
    onResolutionChange: () => {
      updateAspectRatioFromVideo()
    },
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

  // video要素のサイズ変更を監視してレイアウトを更新
  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    const handleResize = () => {
      const { videoWidth, videoHeight } = video
      if (videoWidth > 0 && videoHeight > 0) {
        console.log(`H264Player: Video resolution changed to ${videoWidth}x${videoHeight}`)
      }
      updateAspectRatioFromVideo()
    }

    // loadedmetadata と resize イベントを監視
    video.addEventListener('loadedmetadata', handleResize)
    video.addEventListener('resize', handleResize)

    // 既に metadata が揃っているケースもあるので初回も試行
    handleResize()

    return () => {
      video.removeEventListener('loadedmetadata', handleResize)
      video.removeEventListener('resize', handleResize)
    }
  }, [videoRef, updateAspectRatioFromVideo])

  const resolvedFit: H264PlayerFit = fit
  const resolvedVideoStyle: React.CSSProperties = {
    width: '100%',
    height: 'auto',
    maxHeight,
    display: 'block',
    objectFit: resolvedFit,
    ...videoStyle,
  }

  return (
    <div 
      className={`relative bg-black rounded-lg overflow-hidden ${className}`}
      style={aspectRatio ? { aspectRatio } : undefined}
    >
      <video
        ref={videoRef}
        autoPlay
        muted
        playsInline
        className={videoClassName}
        style={resolvedVideoStyle}
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
