/**
 * Type definitions for react-android-screen
 */

/**
 * ストリームの接続状態
 */
export type StreamStatus = 'disconnected' | 'connecting' | 'connected' | 'error'

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
