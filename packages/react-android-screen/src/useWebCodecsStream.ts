/**
 * useWebCodecsStream - WebCodecs API を使った低遅延 H.264 ストリーミング
 * 
 * MSE を使わず、VideoDecoder で直接デコードして Canvas に描画する。
 * これにより MSE のバッファリング遅延（50-150ms）を回避できる。
 */

import { useRef, useState, useCallback, useEffect } from 'react'
import type { StreamStatus, StreamStats } from './types.js'

export interface UseWebCodecsStreamOptions {
  wsUrl: string
  autoConnect?: boolean
  debug?: boolean
  onConnected?: () => void
  onDisconnected?: () => void
  onError?: (error: string) => void
}

export interface UseWebCodecsStreamResult {
  canvasRef: React.RefObject<HTMLCanvasElement>
  status: StreamStatus
  stats: StreamStats
  connect: () => void
  disconnect: () => void
  isSupported: boolean
}

// NAL unit types
const NAL_TYPE_SPS = 7
const NAL_TYPE_PPS = 8
const NAL_TYPE_IDR = 5
const NAL_TYPE_NON_IDR = 1

/**
 * WebCodecs API がサポートされているかチェック
 */
export function isWebCodecsSupported(): boolean {
  return typeof VideoDecoder !== 'undefined' && typeof EncodedVideoChunk !== 'undefined'
}

/**
 * 2つの Uint8Array が等しいかチェック
 */
function arraysEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false
  }
  return true
}

/**
 * NAL unit から NAL type を取得
 */
function getNalType(nalUnit: Uint8Array): number {
  // start code をスキップして NAL header を取得
  let offset = 0
  if (nalUnit[0] === 0 && nalUnit[1] === 0 && nalUnit[2] === 0 && nalUnit[3] === 1) {
    offset = 4
  } else if (nalUnit[0] === 0 && nalUnit[1] === 0 && nalUnit[2] === 1) {
    offset = 3
  }
  return nalUnit[offset] & 0x1f
}

/**
 * データから NAL units を抽出
 */
function extractNalUnits(data: Uint8Array): Uint8Array[] {
  const nalUnits: Uint8Array[] = []
  let start = -1

  for (let i = 0; i < data.length - 3; i++) {
    // 3-byte または 4-byte start code を検出
    const is4ByteStart = data[i] === 0 && data[i + 1] === 0 && data[i + 2] === 0 && data[i + 3] === 1
    const is3ByteStart = data[i] === 0 && data[i + 1] === 0 && data[i + 2] === 1

    if (is4ByteStart || is3ByteStart) {
      if (start >= 0) {
        nalUnits.push(data.slice(start, i))
      }
      start = i
    }
  }

  if (start >= 0) {
    nalUnits.push(data.slice(start))
  }

  return nalUnits
}

/**
 * NAL unit から start code を除去
 */
function stripStartCode(nalUnit: Uint8Array): Uint8Array {
  if (nalUnit[0] === 0 && nalUnit[1] === 0 && nalUnit[2] === 0 && nalUnit[3] === 1) {
    return nalUnit.slice(4)
  } else if (nalUnit[0] === 0 && nalUnit[1] === 0 && nalUnit[2] === 1) {
    return nalUnit.slice(3)
  }
  return nalUnit
}

/**
 * SPS と PPS から avcC description を構築
 * WebCodecs の VideoDecoderConfig.description に渡す形式
 */
function buildAvcCDescription(sps: Uint8Array, pps: Uint8Array): Uint8Array {
  // avcC box format:
  // - configurationVersion (1 byte) = 1
  // - AVCProfileIndication (1 byte)
  // - profile_compatibility (1 byte)
  // - AVCLevelIndication (1 byte)
  // - lengthSizeMinusOne (1 byte) = 3 (4-byte length prefix)
  // - numOfSequenceParameterSets (1 byte) = 1
  // - SPS length (2 bytes)
  // - SPS data
  // - numOfPictureParameterSets (1 byte) = 1
  // - PPS length (2 bytes)
  // - PPS data

  const avcC = new Uint8Array(11 + sps.length + pps.length)
  let offset = 0

  // configurationVersion
  avcC[offset++] = 1
  // AVCProfileIndication (from SPS)
  avcC[offset++] = sps[1]
  // profile_compatibility (from SPS)
  avcC[offset++] = sps[2]
  // AVCLevelIndication (from SPS)
  avcC[offset++] = sps[3]
  // lengthSizeMinusOne (4-byte NAL unit length - 1 = 3)
  avcC[offset++] = 0xff // 111111 11 = reserved (6 bits) + lengthSizeMinusOne (2 bits) = 3
  // numOfSequenceParameterSets
  avcC[offset++] = 0xe1 // 111 00001 = reserved (3 bits) + numOfSPS (5 bits) = 1
  // SPS length (big-endian)
  avcC[offset++] = (sps.length >> 8) & 0xff
  avcC[offset++] = sps.length & 0xff
  // SPS data
  avcC.set(sps, offset)
  offset += sps.length
  // numOfPictureParameterSets
  avcC[offset++] = 1
  // PPS length (big-endian)
  avcC[offset++] = (pps.length >> 8) & 0xff
  avcC[offset++] = pps.length & 0xff
  // PPS data
  avcC.set(pps, offset)

  return avcC
}

/**
 * SPS/PPS から avc1 コーデック文字列を生成
 */
function buildCodecString(sps: Uint8Array): string {
  // SPS の先頭 3 バイトからプロファイル情報を取得
  // start code をスキップ
  let offset = 0
  if (sps[0] === 0 && sps[1] === 0 && sps[2] === 0 && sps[3] === 1) {
    offset = 5 // 4-byte start code + NAL header
  } else if (sps[0] === 0 && sps[1] === 0 && sps[2] === 1) {
    offset = 4 // 3-byte start code + NAL header
  } else {
    offset = 1 // NAL header のみ
  }

  const profileIdc = sps[offset]
  const profileCompatibility = sps[offset + 1]
  const levelIdc = sps[offset + 2]

  // avc1.XXYYZZ 形式
  const hex = (n: number) => n.toString(16).padStart(2, '0')
  return `avc1.${hex(profileIdc)}${hex(profileCompatibility)}${hex(levelIdc)}`
}

/**
 * WebCodecs を使った Android 画面ストリーミングフック
 */
export function useWebCodecsStream(options: UseWebCodecsStreamOptions): UseWebCodecsStreamResult {
  const {
    wsUrl,
    autoConnect = true,
    debug = false,
    onConnected,
    onDisconnected,
    onError,
  } = options

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const decoderRef = useRef<VideoDecoder | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const [status, setStatus] = useState<StreamStatus>('disconnected')
  const [stats, setStats] = useState<StreamStats>({ bytes: 0, chunks: 0 })
  const isSupported = isWebCodecsSupported()

  // SPS/PPS を保持
  const spsRef = useRef<Uint8Array | null>(null)
  const ppsRef = useRef<Uint8Array | null>(null)
  const isConfiguredRef = useRef(false)
  const timestampRef = useRef(0)
  const frameCountRef = useRef(0)

  // エラー復帰用の状態
  const decodeErrorCountRef = useRef(0)
  const waitingForKeyFrameRef = useRef(false)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const MAX_DECODE_ERRORS = 5  // この回数連続でエラーが発生したらキーフレーム待ち
  const DECODER_ERROR_RECONNECT_DELAY = 1000  // デコーダーエラー時の再接続待機時間

  // コールバックを ref で安定させる
  const onConnectedRef = useRef(onConnected)
  const onDisconnectedRef = useRef(onDisconnected)
  const onErrorRef = useRef(onError)
  const debugRef = useRef(debug)

  // コールバックを同期
  useEffect(() => {
    onConnectedRef.current = onConnected
    onDisconnectedRef.current = onDisconnected
    onErrorRef.current = onError
    debugRef.current = debug
  }, [onConnected, onDisconnected, onError, debug])

  const disconnect = useCallback(() => {
    // 再接続タイマーをクリア
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    if (decoderRef.current) {
      try {
        decoderRef.current.close()
      } catch (e) {
        // ignore
      }
      decoderRef.current = null
    }
    isConfiguredRef.current = false
    spsRef.current = null
    ppsRef.current = null
    decodeErrorCountRef.current = 0
    waitingForKeyFrameRef.current = false
    setStatus('disconnected')
  }, [])

  const connect = useCallback(() => {
    if (!isSupported) {
      onErrorRef.current?.('WebCodecs API is not supported in this browser')
      return
    }

    if (!canvasRef.current) return

    // 既存の接続をクリーンアップ
    disconnect()

    setStatus('connecting')
    setStats({ bytes: 0, chunks: 0 })
    timestampRef.current = 0
    frameCountRef.current = 0

    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      onErrorRef.current?.('Failed to get canvas 2d context')
      return
    }

    // 再接続用のヘルパー関数
    const scheduleReconnect = (reason: string) => {
      console.warn(`[WebCodecs] Scheduling reconnect due to: ${reason}`)
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      reconnectTimeoutRef.current = setTimeout(() => {
        console.log('[WebCodecs] Executing scheduled reconnect...')
        reconnectTimeoutRef.current = null
        // connect を再呼び出し（disconnect は connect 内で行われる）
        connectRef.current()
      }, DECODER_ERROR_RECONNECT_DELAY)
    }

    // VideoDecoder を初期化
    const decoder = new VideoDecoder({
      output: (frame: VideoFrame) => {
        // デコード成功時はエラーカウントをリセット
        decodeErrorCountRef.current = 0
        waitingForKeyFrameRef.current = false

        // Canvas のサイズを動画に合わせる
        if (canvas.width !== frame.displayWidth || canvas.height !== frame.displayHeight) {
          canvas.width = frame.displayWidth
          canvas.height = frame.displayHeight
          if (debugRef.current) {
            console.log(`[WebCodecs] Resolution: ${frame.displayWidth}x${frame.displayHeight}`)
          }
        }

        // フレームを Canvas に描画
        ctx.drawImage(frame, 0, 0)
        frame.close()

        frameCountRef.current++
        if (debugRef.current && frameCountRef.current % 30 === 0) {
          console.log(`[WebCodecs] Frames decoded: ${frameCountRef.current}`)
        }
      },
      error: (e: DOMException) => {
        console.error('[WebCodecs] Decoder error:', e.name, e.message)
        onErrorRef.current?.(`Decoder error: ${e.message}`)
        
        // デコーダーエラー時は再接続をスケジュール
        console.log('[WebCodecs] Decoder entered error state, will attempt recovery...')
        scheduleReconnect(`Decoder error: ${e.message}`)
      },
    })
    decoderRef.current = decoder

    // WebSocket URL を構築
    let fullWsUrl: string
    if (wsUrl.startsWith('ws://') || wsUrl.startsWith('wss://')) {
      fullWsUrl = wsUrl
    } else {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      fullWsUrl = `${protocol}//${window.location.host}${wsUrl}`
    }

    if (debugRef.current) {
      console.log('[WebCodecs] Connecting to:', fullWsUrl)
    }

    const ws = new WebSocket(fullWsUrl)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    let totalBytes = 0
    let totalChunks = 0

    ws.onopen = () => {
      if (debugRef.current) {
        console.log('[WebCodecs] WebSocket connected')
      }
      setStatus('connected')
      onConnectedRef.current?.()
    }

    ws.onmessage = (event) => {
      const data = new Uint8Array(event.data as ArrayBuffer)
      totalBytes += data.length
      totalChunks += 1
      setStats({ bytes: totalBytes, chunks: totalChunks })

      // NAL units を抽出
      const nalUnits = extractNalUnits(data)

      for (const nalUnit of nalUnits) {
        const nalType = getNalType(nalUnit)

        if (nalType === NAL_TYPE_SPS) {
          const newSps = nalUnit
          // SPS が変わったかチェック（解像度変更対応）
          const spsChanged = !spsRef.current || !arraysEqual(spsRef.current, newSps)
          if (spsChanged) {
            if (debugRef.current) {
              console.log('[WebCodecs] SPS received (changed)')
            }
            spsRef.current = newSps
            // SPS が変わったら再構成が必要
            isConfiguredRef.current = false
          }
        } else if (nalType === NAL_TYPE_PPS) {
          const newPps = nalUnit
          const ppsChanged = !ppsRef.current || !arraysEqual(ppsRef.current, newPps)
          if (ppsChanged) {
            if (debugRef.current) {
              console.log('[WebCodecs] PPS received (changed)')
            }
            ppsRef.current = newPps
            // PPS が変わったら再構成が必要
            isConfiguredRef.current = false
          }
        }

        // SPS と PPS が揃ったら decoder を configure
        if (!isConfiguredRef.current && spsRef.current && ppsRef.current) {
          const codecString = buildCodecString(spsRef.current)
          if (debugRef.current) {
            console.log('[WebCodecs] Codec string:', codecString)
          }

          // AVCC format description を構築
          // SPS と PPS から avcC box を作成
          const spsData = stripStartCode(spsRef.current)
          const ppsData = stripStartCode(ppsRef.current)
          const description = buildAvcCDescription(spsData, ppsData)

          try {
            // 既に configure 済みの場合は reset してから再構成
            if (decoder.state === 'configured') {
              if (debugRef.current) {
                console.log('[WebCodecs] Resetting decoder for reconfiguration (resolution change)')
              }
              decoder.reset()
            }

            decoder.configure({
              codec: codecString,
              description: description,
              optimizeForLatency: true,
            })
            isConfiguredRef.current = true
            waitingForKeyFrameRef.current = false
            decodeErrorCountRef.current = 0
            if (debugRef.current) {
              console.log('[WebCodecs] Decoder configured with description')
            }
          } catch (e) {
            console.error('[WebCodecs] Failed to configure decoder:', e)
            onErrorRef.current?.(`Failed to configure decoder: ${e}`)
            return
          }
        }

        // デコーダーが設定済みで、スライスデータの場合はデコード
        if (isConfiguredRef.current && (nalType === NAL_TYPE_IDR || nalType === NAL_TYPE_NON_IDR)) {
          const isKeyFrame = nalType === NAL_TYPE_IDR

          // キーフレーム待ち状態の場合
          if (waitingForKeyFrameRef.current) {
            if (isKeyFrame) {
              console.log('[WebCodecs] Recovery: Received key frame, resuming decode')
              waitingForKeyFrameRef.current = false
              decodeErrorCountRef.current = 0
            } else {
              // 非キーフレームはスキップ
              if (debugRef.current) {
                console.log('[WebCodecs] Skipping non-key frame while waiting for recovery')
              }
              continue
            }
          }

          // デコーダーの状態をチェック
          if (decoder.state === 'closed') {
            console.error('[WebCodecs] Decoder is closed, scheduling reconnect')
            scheduleReconnect('Decoder closed unexpectedly')
            return
          }

          try {
            // Start code を除去して AVCC 形式に変換（4-byte length prefix）
            const nalData = stripStartCode(nalUnit)
            const avccData = new Uint8Array(4 + nalData.length)
            avccData[0] = (nalData.length >> 24) & 0xff
            avccData[1] = (nalData.length >> 16) & 0xff
            avccData[2] = (nalData.length >> 8) & 0xff
            avccData[3] = nalData.length & 0xff
            avccData.set(nalData, 4)

            const chunk = new EncodedVideoChunk({
              type: isKeyFrame ? 'key' : 'delta',
              timestamp: timestampRef.current,
              data: avccData,
            })
            decoder.decode(chunk)
            
            // タイムスタンプを進める（30fps 想定）
            timestampRef.current += 33333 // マイクロ秒
          } catch (e) {
            decodeErrorCountRef.current++
            console.warn(`[WebCodecs] Decode error (${decodeErrorCountRef.current}/${MAX_DECODE_ERRORS}):`, e)
            
            // 連続エラーが閾値を超えたらキーフレーム待ちに移行
            if (decodeErrorCountRef.current >= MAX_DECODE_ERRORS) {
              console.warn('[WebCodecs] Too many decode errors, waiting for next key frame to recover')
              waitingForKeyFrameRef.current = true
              
              // デコーダーをフラッシュしてリセット
              try {
                if (decoder.state === 'configured') {
                  decoder.flush().then(() => {
                    console.log('[WebCodecs] Decoder flushed for recovery')
                  }).catch((flushErr) => {
                    console.warn('[WebCodecs] Flush failed:', flushErr)
                  })
                }
              } catch (flushErr) {
                console.warn('[WebCodecs] Flush error:', flushErr)
              }
            }
          }
        }
      }
    }

    ws.onerror = () => {
      console.error('[WebCodecs] WebSocket error')
      setStatus('error')
      onErrorRef.current?.('WebSocket connection error')
    }

    ws.onclose = (event) => {
      if (debugRef.current) {
        console.log('[WebCodecs] WebSocket closed:', event.code, event.reason)
      }
      setStatus('disconnected')
      onDisconnectedRef.current?.()
    }
  }, [wsUrl, isSupported, disconnect])

  // connect/disconnect を ref で保持
  const connectRef = useRef(connect)
  const disconnectRef = useRef(disconnect)
  useEffect(() => {
    connectRef.current = connect
    disconnectRef.current = disconnect
  }, [connect, disconnect])

  // 自動接続
  useEffect(() => {
    if (autoConnect && isSupported) {
      const timer = setTimeout(() => {
        if (canvasRef.current) {
          connectRef.current()
        }
      }, 100)
      return () => {
        clearTimeout(timer)
        disconnectRef.current()
      }
    }
    return () => {
      disconnectRef.current()
    }
  }, [wsUrl, autoConnect, isSupported])

  return {
    canvasRef,
    status,
    stats,
    connect,
    disconnect,
    isSupported,
  }
}
