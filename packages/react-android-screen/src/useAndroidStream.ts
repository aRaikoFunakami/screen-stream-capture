/**
 * useAndroidStream - Android 画面ストリーミングのカスタムフック
 */

import { useRef, useState, useCallback, useEffect } from 'react'
import JMuxer from 'jmuxer'
import type { StreamStatus, StreamStats, UseAndroidStreamOptions, UseAndroidStreamResult } from './types'

/**
 * Android 画面ストリーミングのためのカスタムフック
 * 
 * @example
 * ```tsx
 * const { videoRef, status, stats, connect, disconnect } = useAndroidStream({
 *   wsUrl: '/api/ws/stream/emulator-5554',
 *   autoConnect: true,
 * })
 * 
 * return <video ref={videoRef} autoPlay muted />
 * ```
 */
export function useAndroidStream(options: UseAndroidStreamOptions): UseAndroidStreamResult {
  const {
    wsUrl,
    autoConnect = true,
    fps = 30,
    onConnected,
    onDisconnected,
    onError,
  } = options

  const videoRef = useRef<HTMLVideoElement>(null)
  const jmuxerRef = useRef<JMuxer | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const [status, setStatus] = useState<StreamStatus>('disconnected')
  const [stats, setStats] = useState<StreamStats>({ bytes: 0, chunks: 0 })

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

  const connect = useCallback(() => {
    if (!videoRef.current) return
    
    // 既存の接続をクリーンアップ
    disconnect()

    setStatus('connecting')
    setStats({ bytes: 0, chunks: 0 })

    // JMuxer を初期化
    const jmuxer = new JMuxer({
      node: videoRef.current,
      mode: 'video',
      fps,
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

    // WebSocket URL を構築
    let fullWsUrl: string
    if (wsUrl.startsWith('ws://') || wsUrl.startsWith('wss://')) {
      fullWsUrl = wsUrl
    } else {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      fullWsUrl = `${protocol}//${window.location.host}${wsUrl}`
    }

    console.log('Connecting to WebSocket:', fullWsUrl)

    const ws = new WebSocket(fullWsUrl)
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

      jmuxer.feed({ video: data })
    }

    ws.onerror = () => {
      console.error('WebSocket error')
      setStatus('error')
      onError?.('WebSocket connection error')
    }

    ws.onclose = (event) => {
      console.log('WebSocket closed:', event.code, event.reason)
      setStatus('disconnected')
      onDisconnected?.()
    }
  }, [wsUrl, fps, disconnect, onConnected, onDisconnected, onError])

  // 自動接続 - wsUrl が変わった時のみ再接続
  useEffect(() => {
    if (autoConnect) {
      // video 要素がマウントされてから接続
      const timer = setTimeout(() => {
        if (videoRef.current) {
          connect()
        }
      }, 100)
      return () => {
        clearTimeout(timer)
        disconnect()
      }
    }
    return () => {
      disconnect()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wsUrl, autoConnect])

  return {
    videoRef,
    status,
    stats,
    connect,
    disconnect,
  }
}
