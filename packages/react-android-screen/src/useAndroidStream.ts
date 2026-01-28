/**
 * useAndroidStream - Android 画面ストリーミングのカスタムフック
 */

import { useRef, useState, useCallback, useEffect } from 'react'
import JMuxer from 'jmuxer'
import type { StreamStatus, StreamStats, UseAndroidStreamOptions, UseAndroidStreamResult } from './types.js'

/**
 * H.264 NAL unit からSPS（Sequence Parameter Set）を検出し、解像度情報を抽出する簡易パーサー。
 * 解像度変更検出用。完全なパースではなく、SPSの存在と基本的な解像度を取得する。
 */
function findSpsNalUnit(data: Uint8Array): Uint8Array | null {
  // NAL start code を探す (0x00 0x00 0x00 0x01 または 0x00 0x00 0x01)
  for (let i = 0; i < data.length - 4; i++) {
    let nalStart = -1
    if (data[i] === 0 && data[i + 1] === 0 && data[i + 2] === 0 && data[i + 3] === 1) {
      nalStart = i + 4
    } else if (data[i] === 0 && data[i + 1] === 0 && data[i + 2] === 1) {
      nalStart = i + 3
    }
    
    if (nalStart >= 0 && nalStart < data.length) {
      const nalType = data[nalStart] & 0x1f
      // NAL type 7 = SPS
      if (nalType === 7) {
        // 次のstart codeまで、またはデータ終端までをSPSとして返す
        for (let j = nalStart; j < data.length - 3; j++) {
          if ((data[j] === 0 && data[j + 1] === 0 && data[j + 2] === 0 && data[j + 3] === 1) ||
              (data[j] === 0 && data[j + 1] === 0 && data[j + 2] === 1)) {
            return data.slice(nalStart, j)
          }
        }
        return data.slice(nalStart)
      }
    }
  }
  return null
}

/**
 * 2つのUint8Arrayが等しいか比較
 */
function uint8ArrayEqual(a: Uint8Array | null, b: Uint8Array | null): boolean {
  if (a === null && b === null) return true
  if (a === null || b === null) return false
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false
  }
  return true
}

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
    onResolutionChange,
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
    let lastSps: Uint8Array | null = null
    let isResetting = false  // リセット中フラグ
    let pendingData: Uint8Array[] = []  // リセット中にバッファするデータ

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

      // リセット中はデータを無視
      if (isResetting) {
        // リセット中のデータをバッファ
        pendingData.push(data)
        return
      }

      // SPS（解像度情報）の変更を検出
      const sps = findSpsNalUnit(data)
      if (sps !== null) {
        if (lastSps === null) {
          // 最初のSPS検出時は記録するだけ
          console.log('Initial SPS detected')
          lastSps = sps
        } else if (!uint8ArrayEqual(sps, lastSps)) {
          // 2回目以降のSPS変更時のみリセット
          console.log('SPS changed (resolution change detected), resetting JMuxer')
          lastSps = sps
        
          // JMuxerをリセット（解像度変更に対応）
          if (jmuxerRef.current && videoRef.current) {
            const video = videoRef.current
            const oldJmuxer = jmuxerRef.current
            jmuxerRef.current = null
            isResetting = true
            // 現在のデータをペンディングに追加（SPSを含む）
            pendingData = [data]
          
            // 古いJMuxerを破棄し、videoのsrcもクリア
            oldJmuxer.destroy()
            video.removeAttribute('src')
            video.load()
          
            // 少し待機してから新しいJMuxerを作成（MediaSourceのクリーンアップ待ち）
            setTimeout(() => {
              const newJmuxer = new JMuxer({
                node: video,
                mode: 'video',
                fps,
                flushingTime: 100,
                debug: false,
                onReady: () => {
                  console.log('JMuxer ready (after reset)')
                  // バッファしたデータをフィード
                  for (const bufferedData of pendingData) {
                    newJmuxer.feed({ video: bufferedData })
                  }
                  pendingData = []
                  isResetting = false
                },
                onError: (error: Error) => {
                  console.error('JMuxer error:', error)
                  onError?.(error.message)
                },
              })
              jmuxerRef.current = newJmuxer
              // 解像度変更を通知
              onResolutionChange?.()
            }, 100)
            return
          }
        }
      }

      jmuxerRef.current?.feed({ video: data })
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
  }, [wsUrl, fps, onConnected, onDisconnected, onError])

  // disconnect を ref に保存して依存配列の問題を回避
  const disconnectRef = useRef(disconnect)
  disconnectRef.current = disconnect

  // 自動接続 - wsUrl が変わった時のみ再接続
  useEffect(() => {
    let mounted = true
    let timer: ReturnType<typeof setTimeout> | null = null

    if (autoConnect) {
      // video 要素がマウントされてから接続
      timer = setTimeout(() => {
        if (mounted && videoRef.current) {
          connect()
        }
      }, 100)
    }

    return () => {
      mounted = false
      if (timer) {
        clearTimeout(timer)
      }
      disconnectRef.current()
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
