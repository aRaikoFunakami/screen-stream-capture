/**
 * Type definitions for react-android-screen
 */

/**
 * ストリームの接続状態
 */
export type StreamStatus = 'disconnected' | 'connecting' | 'connected' | 'error'

/**
 * LiveSync のモード
 * - 'seek': 従来のシークベースの同期 (Chrome 向き)
 * - 'playbackRate': 再生速度調整による同期 (Firefox 向き、スムーズ)
 * - 'hybrid': 通常は playbackRate、極端な遅延時のみ seek (デフォルト)
 */
export type LiveSyncMode = 'seek' | 'playbackRate' | 'hybrid'

/**
 * ストリーム統計情報
 */
export interface StreamStats {
  /** 受信したバイト数 */
  bytes: number
  /** 受信したチャンク数 */
  chunks: number
}

/**
 * H264Player の表示フィットモード（CSS object-fit）
 */
export type H264PlayerFit = 'contain' | 'cover' | 'fill' | 'none' | 'scale-down'

/**
 * H264Player コンポーネントの Props
 */
export interface H264PlayerProps {
  /** WebSocket URL (例: "/api/ws/stream/emulator-5554" or "ws://localhost:8000/api/ws/stream/emulator-5554") */
  wsUrl: string
  /** CSS クラス名 */
  className?: string
  /** video 要素に付与する CSS クラス名 */
  videoClassName?: string
  /** video 要素の style（デフォルトの style を上書き可能） */
  videoStyle?: React.CSSProperties
  /** 画像のフィット（CSS object-fit、デフォルト: contain） */
  fit?: H264PlayerFit
  /** video の最大高さ（デフォルト: 70vh）。例: '100%', '70vh' */
  maxHeight?: string
  /** 接続時のコールバック */
  onConnected?: () => void
  /** 切断時のコールバック */
  onDisconnected?: () => void
  /** エラー時のコールバック */
  onError?: (error: string) => void
  /** JMuxer のフレームレート (デフォルト: 30) */
  fps?: number
  /** ライブ配信として遅延が溜まった場合に追従シークする (デフォルト: true) */
  liveSync?: boolean
  /** LiveSync のモード: 'seek' | 'playbackRate' | 'hybrid' (デフォルト: 'hybrid') */
  liveSyncMode?: LiveSyncMode
  /** 許容遅延 (ミリ秒, デフォルト: 1500) */
  maxLatencyMs?: number
  /** 追従後に保つ遅延 (ミリ秒, デフォルト: 300) */
  targetLatencyMs?: number
  /** 固まり検知と自動復旧を有効化 (デフォルト: true) */
  stallRecovery?: boolean
  /** 固まり判定: 再生時刻が進まない許容時間 (ミリ秒, デフォルト: 2000) */
  stallTimeoutMs?: number
  /** 自動復旧の最大回数 (デフォルト: 3) */
  maxRecoveries?: number
  /** 復旧試行の最小間隔 (ミリ秒, デフォルト: 1000) */
  recoveryCooldownMs?: number
  /** デバッグログを有効化 (デフォルト: false) */
  debug?: boolean
  /** 自動再接続 (デフォルト: true) */
  autoReconnect?: boolean
  /** 再接続間隔 (ミリ秒, デフォルト: 3000) */
  reconnectInterval?: number
}

/**
 * useAndroidStream フックのオプション
 */
export interface UseAndroidStreamOptions {
  /** WebSocket URL */
  wsUrl: string
  /** 自動接続 (デフォルト: true) */
  autoConnect?: boolean
  /** JMuxer のフレームレート (デフォルト: 30) */
  fps?: number
  /** ライブ配信として遅延が溜まった場合に追従シークする (デフォルト: true) */
  liveSync?: boolean
  /** LiveSync のモード: 'seek' | 'playbackRate' | 'hybrid' (デフォルト: 'hybrid') */
  liveSyncMode?: LiveSyncMode
  /** 許容遅延 (ミリ秒, デフォルト: 1500) */
  maxLatencyMs?: number
  /** 追従後に保つ遅延 (ミリ秒, デフォルト: 300) */
  targetLatencyMs?: number
  /** 固まり検知と自動復旧を有効化 (デフォルト: true) */
  stallRecovery?: boolean
  /** 固まり判定: 再生時刻が進まない許容時間 (ミリ秒, デフォルト: 2000) */
  stallTimeoutMs?: number
  /** 自動復旧の最大回数 (デフォルト: 3) */
  maxRecoveries?: number
  /** 復旧試行の最小間隔 (ミリ秒, デフォルト: 1000) */
  recoveryCooldownMs?: number
  /** デバッグログを有効化 (デフォルト: false) */
  debug?: boolean
  /** 接続時のコールバック */
  onConnected?: () => void
  /** 切断時のコールバック */
  onDisconnected?: () => void
  /** エラー時のコールバック */
  onError?: (error: string) => void
  /** 解像度変更時のコールバック */
  onResolutionChange?: () => void
}

/**
 * useAndroidStream フックの戻り値
 */
export interface UseAndroidStreamResult {
  /** video 要素の ref */
  videoRef: React.RefObject<HTMLVideoElement>
  /** 接続状態 */
  status: StreamStatus
  /** ストリーム統計 */
  stats: StreamStats
  /** 接続を開始 */
  connect: () => void
  /** 切断 */
  disconnect: () => void
}
