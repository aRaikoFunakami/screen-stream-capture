import { useEffect, useRef, useCallback, useState } from 'react'
import JMuxer from 'jmuxer'

interface H264PlayerProps {
  serial: string
  onError?: (error: string) => void
  onConnected?: () => void
  onDisconnected?: () => void
}

export function H264Player({ serial, onError, onConnected, onDisconnected }: H264PlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const jmuxerRef = useRef<JMuxer | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const [status, setStatus] = useState<'connecting' | 'connected' | 'disconnected' | 'error'>('disconnected')
  const [stats, setStats] = useState({ bytes: 0, chunks: 0 })

  const connect = useCallback(() => {
    if (!videoRef.current) return

    setStatus('connecting')

    // JMuxer を初期化
    const jmuxer = new JMuxer({
      node: videoRef.current,
      mode: 'video',
      fps: 30,
      flushingTime: 100,
      debug: false,
      onReady: () => {
        console.log('JMuxer ready')
      },
      onError: (error: Error) => {
        console.error('JMuxer error:', error)
        onError?.(error.message)
      },
    })
    jmuxerRef.current = jmuxer

    // WebSocket 接続
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/ws/stream/${serial}`
    console.log('Connecting to WebSocket:', wsUrl)

    const ws = new WebSocket(wsUrl)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    let totalBytes = 0
    let totalChunks = 0

    ws.onopen = () => {
      console.log('WebSocket connected')
      setStatus('connected')
      onConnected?.()
    }

    ws.onmessage = (event) => {
      const data = new Uint8Array(event.data as ArrayBuffer)
      totalBytes += data.length
      totalChunks += 1
      setStats({ bytes: totalBytes, chunks: totalChunks })

      // JMuxer に H.264 データを送信
      jmuxer.feed({
        video: data,
      })
    }

    ws.onerror = (event) => {
      console.error('WebSocket error:', event)
      setStatus('error')
      onError?.('WebSocket connection error')
    }

    ws.onclose = (event) => {
      console.log('WebSocket closed:', event.code, event.reason)
      setStatus('disconnected')
      onDisconnected?.()
    }
  }, [serial, onError, onConnected, onDisconnected])

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    if (jmuxerRef.current) {
      jmuxerRef.current.destroy()
      jmuxerRef.current = null
    }
    setStatus('disconnected')
  }, [])

  // 接続開始・クリーンアップ
  useEffect(() => {
    connect()
    return () => {
      disconnect()
    }
  }, [serial, connect, disconnect])

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`
  }

  return (
    <div className="relative bg-black rounded-lg overflow-hidden">
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
        <span
          className={`w-2 h-2 rounded-full ${
            status === 'connected'
              ? 'bg-green-500'
              : status === 'connecting'
              ? 'bg-yellow-500 animate-pulse'
              : status === 'error'
              ? 'bg-red-500'
              : 'bg-gray-500'
          }`}
        />
        <span>
          {status === 'connected'
            ? 'ライブ'
            : status === 'connecting'
            ? '接続中...'
            : status === 'error'
            ? 'エラー'
            : '切断'}
        </span>
      </div>

      {/* 統計情報 */}
      {status === 'connected' && (
        <div className="absolute bottom-2 left-2 bg-black/50 text-white px-2 py-1 rounded text-xs">
          {formatBytes(stats.bytes)} / {stats.chunks} chunks
        </div>
      )}

      {/* 再接続ボタン */}
      {status === 'disconnected' || status === 'error' ? (
        <div className="absolute inset-0 flex items-center justify-center bg-black/70">
          <button
            onClick={connect}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors"
          >
            再接続
          </button>
        </div>
      ) : null}
    </div>
  )
}
