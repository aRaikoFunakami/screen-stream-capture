/**
 * useAndroidStream - Android 画面ストリーミングのカスタムフック
 */

import { useRef, useState, useCallback, useEffect } from 'react'
import JMuxer from 'jmuxer'
import type { StreamStatus, StreamStats, UseAndroidStreamOptions, UseAndroidStreamResult } from './types.js'

export interface LiveSyncConfig {
  maxLatencyMs: number
  targetLatencyMs: number
}

export interface BufferedTimeRange {
  start: number
  end: number
}

export function isPlaybackStalled(nowMs: number, lastProgressAtMs: number, stallTimeoutMs: number): boolean {
  if (!Number.isFinite(nowMs) || !Number.isFinite(lastProgressAtMs)) return false
  if (!Number.isFinite(stallTimeoutMs) || stallTimeoutMs <= 0) return false
  return nowMs - lastProgressAtMs > stallTimeoutMs
}

export function computeLiveSyncSeekTime(
  currentTime: number,
  bufferedEnd: number,
  config: LiveSyncConfig,
): number | null {
  if (!Number.isFinite(currentTime) || !Number.isFinite(bufferedEnd)) return null
  if (bufferedEnd <= 0) return null
  const maxLatencySec = config.maxLatencyMs / 1000
  const targetLatencySec = config.targetLatencyMs / 1000
  if (maxLatencySec <= 0) return null

  const latencySec = bufferedEnd - currentTime
  if (latencySec <= maxLatencySec) return null

  const targetTime = bufferedEnd - Math.max(targetLatencySec, 0)
  return Math.max(0, targetTime)
}

export function computeLiveSyncSeekTimeInBufferedRange(
  currentTime: number,
  range: BufferedTimeRange,
  config: LiveSyncConfig,
  safetyMarginSec: number,
): number | null {
  if (!Number.isFinite(range.start) || !Number.isFinite(range.end)) return null
  if (range.end <= range.start) return null

  const safeEnd = Math.max(range.start, range.end - Math.max(0, safetyMarginSec))
  const seekTo = computeLiveSyncSeekTime(currentTime, safeEnd, config)
  if (seekTo === null) return null

  if (seekTo < range.start) return range.start
  if (seekTo > safeEnd) return safeEnd
  return seekTo
}

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
    liveSync = true,
    liveSyncMode = 'hybrid',
    maxLatencyMs = 1500,
    targetLatencyMs = 300,
    stallRecovery = true,
    stallTimeoutMs = 2000,
    maxRecoveries = 3,
    recoveryCooldownMs = 1000,
    debug = false,
    onConnected,
    onDisconnected,
    onError,
    onResolutionChange,
  } = options

  const videoRef = useRef<HTMLVideoElement>(null)
  const jmuxerRef = useRef<JMuxer | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const liveSyncIntervalRef = useRef<number | null>(null)
  const videoEventsCleanupRef = useRef<(() => void) | null>(null)
  const lastPlaybackProgressAtRef = useRef<number>(0)
  const lastPlaybackTimeRef = useRef<number>(0)
  const recoveryStageRef = useRef<'seek' | 'jmuxer' | 'reconnect'>('seek')
  const recoveriesRef = useRef<number>(0)
  const lastRecoveryAtRef = useRef<number>(0)
  const [status, setStatus] = useState<StreamStatus>('disconnected')
  const [stats, setStats] = useState<StreamStats>({ bytes: 0, chunks: 0 })

  const disconnect = useCallback(() => {
    if (videoEventsCleanupRef.current) {
      videoEventsCleanupRef.current()
      videoEventsCleanupRef.current = null
    }
    if (liveSyncIntervalRef.current !== null) {
      window.clearInterval(liveSyncIntervalRef.current)
      liveSyncIntervalRef.current = null
    }
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
      flushingTime: 10,
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

    const video = videoRef.current
    const liveSyncConfig: LiveSyncConfig = { maxLatencyMs, targetLatencyMs }
    let lastLiveSyncAt = 0
    let lastTelemetryAt = 0

    recoveryStageRef.current = 'seek'
    recoveriesRef.current = 0
    lastRecoveryAtRef.current = 0

    const markPlaybackProgress = () => {
      const now = performance.now()
      const t = video.currentTime
      if (!Number.isFinite(t)) return
      if (t > lastPlaybackTimeRef.current + 0.001) {
        lastPlaybackTimeRef.current = t
        lastPlaybackProgressAtRef.current = now
        recoveryStageRef.current = 'seek'
      }
    }

    // detach old listeners if any (should be cleaned up by disconnect, but be defensive)
    if (videoEventsCleanupRef.current) {
      videoEventsCleanupRef.current()
      videoEventsCleanupRef.current = null
    }

    const onTimeUpdate = () => {
      markPlaybackProgress()
    }
    const onPlaying = () => {
      // resume: mark as progress baseline
      lastPlaybackTimeRef.current = video.currentTime
      lastPlaybackProgressAtRef.current = performance.now()
      recoveryStageRef.current = 'seek'
    }

    video.addEventListener('timeupdate', onTimeUpdate)
    video.addEventListener('playing', onPlaying)
    videoEventsCleanupRef.current = () => {
      video.removeEventListener('timeupdate', onTimeUpdate)
      video.removeEventListener('playing', onPlaying)
    }

    // initialize progress baseline
    lastPlaybackTimeRef.current = video.currentTime
    lastPlaybackProgressAtRef.current = performance.now()

    const seekToLiveEdge = (): boolean => {
      if (!video) return false
      if (video.readyState < 2) return false
      if (video.buffered.length === 0) return false

      const lastIndex = video.buffered.length - 1
      const range = {
        start: video.buffered.start(lastIndex),
        end: video.buffered.end(lastIndex),
      }

      const safeEnd = Math.max(range.start, range.end - 0.1)
      const targetLatencySec = targetLatencyMs / 1000
      const desired = safeEnd - Math.max(0, targetLatencySec)
      const seekTo = Math.min(safeEnd, Math.max(range.start, desired))

      try {
        video.currentTime = seekTo
        return true
      } catch (e) {
        console.warn('Live edge seek failed:', e)
        return false
      }
    }

    /**
     * LiveSync: 遅延に応じて再生位置を調整する
     * 
     * モード別の動作:
     * - 'seek': 従来のシークベースの同期。遅延が閾値を超えたらシーク。
     * - 'playbackRate': 再生速度調整のみ。シークせずスムーズにキャッチアップ。
     * - 'hybrid': 通常は playbackRate、極端な遅延（3秒以上）時のみシーク。
     */
    const maybeLiveSync = () => {
      if (!liveSync) return
      if (!video) return
      if (video.readyState < 2) return
      if (video.buffered.length === 0) return

      const lastIndex = video.buffered.length - 1
      const range = {
        start: video.buffered.start(lastIndex),
        end: video.buffered.end(lastIndex),
      }
      const safeEnd = Math.max(range.start, range.end - 0.1)
      const latencySec = safeEnd - video.currentTime

      // Telemetry logging (debug mode)
      if (debug) {
        const now = performance.now()
        if (now - lastTelemetryAt > 2000) {
          lastTelemetryAt = now
          console.log('LiveSync telemetry', {
            currentTime: video.currentTime,
            range,
            latencySec,
            maxLatencyMs,
            targetLatencyMs,
            playbackRate: video.playbackRate,
            liveSyncMode,
          })
        }
      }

      const now = performance.now()
      if (now - lastLiveSyncAt < 250) return
      lastLiveSyncAt = now

      const maxLatencySec = maxLatencyMs / 1000
      const targetLatencySec = targetLatencyMs / 1000
      
      // 極端な遅延の閾値（3秒）- hybrid モードでシークを使う閾値
      const extremeLatencyThresholdSec = 3.0

      // playbackRate モードまたは hybrid モード（極端な遅延でない場合）
      if (liveSyncMode === 'playbackRate' || 
          (liveSyncMode === 'hybrid' && latencySec < extremeLatencyThresholdSec)) {
        // playbackRate による gradual catch-up
        // 遅延に応じて再生速度を調整:
        // - 遅延が target 以下: 1.0 (通常速度)
        // - 遅延が target ～ max: 1.0 ～ 1.15 (徐々に加速)
        // - 遅延が max 以上: 1.2 (最大加速)
        let desiredRate = 1.0
        if (latencySec > maxLatencySec) {
          desiredRate = 1.2
        } else if (latencySec > targetLatencySec) {
          // 線形補間: targetLatency で 1.0、maxLatency で 1.15
          const ratio = (latencySec - targetLatencySec) / (maxLatencySec - targetLatencySec)
          desiredRate = 1.0 + ratio * 0.15
        } else if (latencySec < targetLatencySec * 0.5) {
          // 遅延が target の半分以下なら、少し遅くして安定させる
          desiredRate = 0.95
        }

        // 現在の playbackRate と大きく異なる場合のみ変更（頻繁な変更を避ける）
        if (Math.abs(video.playbackRate - desiredRate) > 0.02) {
          video.playbackRate = desiredRate
          if (debug) {
            console.log('LiveSync playbackRate adjusted', {
              latencySec,
              desiredRate,
              previousRate: video.playbackRate,
            })
          }
        }
        return
      }

      // seek モードまたは hybrid モードで極端な遅延の場合
      const seekTo = computeLiveSyncSeekTimeInBufferedRange(video.currentTime, range, liveSyncConfig, 0.1)
      if (seekTo === null) return

      try {
        video.currentTime = seekTo
        // シーク後は playbackRate をリセット
        if (video.playbackRate !== 1.0) {
          video.playbackRate = 1.0
        }
        if (debug) {
          console.log('LiveSync seek applied', {
            seekTo,
            range,
            maxLatencyMs,
            targetLatencyMs,
            latencySec: safeEnd - seekTo,
          })
        }
      } catch (e) {
        console.warn('LiveSync seek failed:', e)
      }
    }

    const resetJmuxer = () => {
      if (!jmuxerRef.current) return

      const oldJmuxer = jmuxerRef.current
      jmuxerRef.current = null
      isResetting = true

      pendingData = []
      oldJmuxer.destroy()
      video.removeAttribute('src')
      video.load()

      setTimeout(() => {
        const newJmuxer = new JMuxer({
          node: video,
          mode: 'video',
          fps,
          flushingTime: 10,
          debug: false,
          onReady: () => {
            console.log('JMuxer ready (after stall recovery reset)')
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
      }, 100)
    }

    const maybeRecoverFromStall = () => {
      if (!stallRecovery) return
      if (isResetting) return
      if (!video) return
      if (video.paused || video.ended) return
      if (video.seeking) return
      if (video.readyState < 2) return
      if (totalChunks < 3) return

      // Background tabs can heavily throttle timers/events; avoid false positives.
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return

      const now = performance.now()
      if (!isPlaybackStalled(now, lastPlaybackProgressAtRef.current, stallTimeoutMs)) return

      if (recoveriesRef.current >= maxRecoveries) {
        onError?.('Playback stalled (recovery limit reached)')
        setStatus('error')
        return
      }

      if (now - lastRecoveryAtRef.current < recoveryCooldownMs) return
      lastRecoveryAtRef.current = now
      recoveriesRef.current += 1

      const stage = recoveryStageRef.current
      console.warn(`Playback stalled, attempting recovery stage=${stage} (${recoveriesRef.current}/${maxRecoveries})`)

      if (stage === 'seek') {
        // even if latency isn't high, try to jump to the live edge of buffered range
        const ok = seekToLiveEdge()
        if (debug) console.log('StallRecovery seek', { ok })
        recoveryStageRef.current = 'jmuxer'
        return
      }

      if (stage === 'jmuxer') {
        resetJmuxer()
        if (debug) console.log('StallRecovery jmuxer reset')
        recoveryStageRef.current = 'reconnect'
        return
      }

      // reconnect
      recoveryStageRef.current = 'seek'
      disconnect()
      window.setTimeout(() => {
        if (debug) console.log('StallRecovery reconnect')
        connect()
      }, 200)
    }

    if (liveSyncIntervalRef.current !== null) {
      window.clearInterval(liveSyncIntervalRef.current)
      liveSyncIntervalRef.current = null
    }
    liveSyncIntervalRef.current = window.setInterval(() => {
      maybeLiveSync()
      maybeRecoverFromStall()
    }, 500)

    ws.onopen = () => {
      console.log('WebSocket connected')
      setStatus('connected')
      onConnected?.()
    }

    ws.onmessage = (event) => {
      const wsRecvTime = performance.now()
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
                flushingTime: 10,
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
      
      // フロントエンド処理時間を計測（WebSocket受信→JMuxer feed完了）
      const feedDoneTime = performance.now()
      const frontendProcessMs = feedDoneTime - wsRecvTime
      if (debug && totalChunks % 30 === 0) {
        console.log(`[FRONTEND_LATENCY] chunk=${totalChunks} size=${data.length} process_ms=${frontendProcessMs.toFixed(3)}`)
      }
      
      maybeLiveSync()
      markPlaybackProgress()
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
      if (videoEventsCleanupRef.current) {
        videoEventsCleanupRef.current()
        videoEventsCleanupRef.current = null
      }
      if (liveSyncIntervalRef.current !== null) {
        window.clearInterval(liveSyncIntervalRef.current)
        liveSyncIntervalRef.current = null
      }
    }
  }, [
    wsUrl,
    fps,
    liveSync,
    maxLatencyMs,
    targetLatencyMs,
    stallRecovery,
    stallTimeoutMs,
    maxRecoveries,
    recoveryCooldownMs,
    debug,
    onConnected,
    onDisconnected,
    onError,
    onResolutionChange,
    disconnect,
  ])

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
