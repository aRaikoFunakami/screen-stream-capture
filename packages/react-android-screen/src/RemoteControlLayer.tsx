/**
 * RemoteControlLayer - 映像(H264Player)の上に重ねて、クリック/タップ・ホイール・キー・文字を操作チャネルへ送る部品
 *
 * H264Player の children として置き、onVideoRef で受け取った <video> を videoEl に渡す。
 * 配信の WebSocket には触れず、操作用の WebSocket を別に開く(閲覧と操作で許可を分けられる)。
 * 接続直後に {"type":"auth","token":authToken} を送り、{"type":"ready"} を受けてから入力を送る
 * (トークンを URL に載せない)。座標は object-fit の余白を除いた映像の表示領域に対する 0..1 で送る。
 * 文字は隠し textarea の input / compositionend(IME の確定)から取り、日本語も確定後の文字列で送る。
 * 制御メッセージの形は web-screen-stream / android-screen-stream と同じ。
 */

import { useCallback, useEffect, useRef, useState } from 'react'

export type RemoteControlStatus = 'connecting' | 'ready' | 'closed' | 'error'

export interface RemoteControlLayerProps {
  /** 操作用 WebSocket の URL(相対パス可) */
  controlUrl: string
  /** 接続直後の auth メッセージで送るトークン */
  authToken?: string
  /** 座標の基準にする <video>(H264Player の onVideoRef で受け取る) */
  videoEl: HTMLVideoElement | null
  /** 映像の object-fit(H264Player の fit と同じ値) */
  fit?: 'contain' | 'cover'
  onStatus?: (status: RemoteControlStatus, detail?: string) => void
}

const MAX_TEXT_LEN = 256  // サーバ側(android-screen-stream)の 1 メッセージの上限

/** 長い文字列(貼り付けなど)をサーバの上限以下に分ける。サロゲートペアは分けない。 */
export function chunkText(text: string, size = MAX_TEXT_LEN): string[] {
  const chars = Array.from(text)
  const out: string[] = []
  for (let i = 0; i < chars.length; i += size) out.push(chars.slice(i, i + size).join(''))
  return out
}

const SPECIAL_KEYS = new Set(['Enter', 'Backspace', 'Tab', 'Escape', 'Delete', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'])

/**
 * 画面上の点を、object-fit で縮小・余白付きで表示された映像の中の 0..1 座標へ変換する。映像の外なら null。
 */
export function mapToVideo(
  clientX: number, clientY: number,
  rect: { left: number; top: number; width: number; height: number },
  videoWidth: number, videoHeight: number, fit: 'contain' | 'cover' = 'contain',
): { x: number; y: number } | null {
  if (!videoWidth || !videoHeight || !rect.width || !rect.height) return null
  const scale = fit === 'contain'
    ? Math.min(rect.width / videoWidth, rect.height / videoHeight)
    : Math.max(rect.width / videoWidth, rect.height / videoHeight)
  const w = videoWidth * scale, h = videoHeight * scale
  const x = (clientX - rect.left - (rect.width - w) / 2) / w
  const y = (clientY - rect.top - (rect.height - h) / 2) / h
  if (x < 0 || x > 1 || y < 0 || y > 1) return null
  return { x, y }
}

function toAbsoluteWsUrl(url: string): string {
  if (url.startsWith('ws://') || url.startsWith('wss://')) return url
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}${url.startsWith('/') ? url : `/${url}`}`
}

export function RemoteControlLayer({ controlUrl, authToken, videoEl, fit = 'contain', onStatus }: RemoteControlLayerProps) {
  const wsRef = useRef<WebSocket | null>(null)
  const kbdRef = useRef<HTMLTextAreaElement | null>(null)
  const seqRef = useRef(0)
  const downRef = useRef<number | null>(null)  // 押している pointerId(1 本指のみ)
  const lastRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 })  // 映像の外で離したときに使う最後の位置
  const composingRef = useRef(false)
  const wheelRef = useRef<{ dy: number; p: { x: number; y: number }; timer: ReturnType<typeof setTimeout> | null }>({ dy: 0, p: { x: 0, y: 0 }, timer: null })
  const readyRef = useRef(false)  // ready 受信後〜切断まで。個々のメッセージの error では止めない
  const [status, setStatus] = useState<RemoteControlStatus>('connecting')

  // onStatus は呼び出し側で毎回作り直されがちなので ref で持つ(依存に入れると描画のたびに WebSocket を張り直してしまう)
  const onStatusRef = useRef(onStatus)
  useEffect(() => { onStatusRef.current = onStatus }, [onStatus])
  const report = useCallback((s: RemoteControlStatus, detail?: string) => {
    setStatus(s)
    onStatusRef.current?.(s, detail)
  }, [])

  useEffect(() => {
    const ws = new WebSocket(toAbsoluteWsUrl(controlUrl))
    wsRef.current = ws
    readyRef.current = false
    report('connecting')
    ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token: authToken ?? '' }))
    ws.onmessage = (ev) => {
      try {
        const m = JSON.parse(ev.data as string)
        if (m.type === 'ready') { readyRef.current = true; report('ready') }
        // 1 件の失敗(ack の代わりの error)は通知だけ。接続も ready の表示もそのまま使い続ける
        else if (m.type === 'error') onStatusRef.current?.('error', String(m.error))
      } catch { /* 応答は JSON のみ。壊れた応答は無視する */ }
    }
    ws.onclose = (ev) => { readyRef.current = false; report('closed', ev.reason || String(ev.code)) }
    return () => {
      // 張り直し・アンマウント時は古い接続の通知を止める(新しい接続の状態を上書きしない)
      ws.onopen = ws.onmessage = ws.onclose = null
      ws.close()
      if (wsRef.current === ws) wsRef.current = null
      readyRef.current = false
    }
  }, [controlUrl, authToken, report])

  const send = useCallback((msg: Record<string, unknown>) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN && readyRef.current) {
      ws.send(JSON.stringify({ ...msg, seq: ++seqRef.current }))
    }
  }, [])
  const sendText = useCallback((text: string) => {
    for (const t of chunkText(text)) send({ type: 'text', text: t })
  }, [send])

  const point = useCallback((e: { clientX: number; clientY: number }) => {
    if (!videoEl) return null
    return mapToVideo(e.clientX, e.clientY, videoEl.getBoundingClientRect(), videoEl.videoWidth, videoEl.videoHeight, fit)
  }, [videoEl, fit])

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!e.isPrimary || e.button !== 0) return  // 右・中クリック、2 本目の指はタップにしない
    const p = point(e)
    if (!p) return
    e.preventDefault()
    downRef.current = e.pointerId
    lastRef.current = p
    e.currentTarget.setPointerCapture(e.pointerId)
    send({ type: 'pointer', action: 'down', ...p })
    kbdRef.current?.focus({ preventScroll: true })
  }
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (downRef.current !== e.pointerId) return
    const p = point(e)
    if (p) { lastRef.current = p; send({ type: 'pointer', action: 'move', ...p }) }
  }
  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (downRef.current !== e.pointerId) return
    downRef.current = null
    send({ type: 'pointer', action: 'up', ...(point(e) ?? lastRef.current) })
    kbdRef.current?.focus({ preventScroll: true })
  }
  // トラックパッドは 1 秒に数十回 wheel を出すので、100ms ごとにまとめて送る(サーバは wheel ごとに画面サイズを読む)
  const onWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    const p = point(e)
    if (!p) return
    const w = wheelRef.current
    w.dy += e.deltaY
    w.p = p
    if (w.timer) return
    w.timer = setTimeout(() => {
      const dy = Math.max(-10, Math.min(10, Math.round(w.dy / 100) || Math.sign(w.dy)))
      w.dy = 0
      w.timer = null
      if (dy) send({ type: 'wheel', ...w.p, dy })
    }, 100)
  }
  useEffect(() => () => { const t = wheelRef.current.timer; if (t) clearTimeout(t) }, [])

  return (
    <div
      data-testid="remote-control-layer"
      data-status={status}
      className="absolute inset-0 z-10"
      style={{ cursor: status === 'ready' ? 'crosshair' : 'not-allowed', touchAction: 'none' }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onContextMenu={(e) => e.preventDefault()}
      onLostPointerCapture={onPointerUp}
      onWheel={onWheel}
    >
      <textarea
        ref={kbdRef}
        aria-label="remote keyboard input"
        autoComplete="off"
        style={{ position: 'absolute', left: -9999, width: 1, height: 1, opacity: 0 }}
        onCompositionStart={() => { composingRef.current = true }}
        onCompositionEnd={(e) => {
          composingRef.current = false
          if (e.data) sendText(e.data)
          e.currentTarget.value = ''
        }}
        onInput={(e) => {
          // 貼り付け(insertFromPaste)は data が null なので、textarea の値をそのまま送る
          const ne = e.nativeEvent as InputEvent
          // IME の確定は compositionend で送る。Safari は compositionend の後に確定分の input も出すので二重に送らない
          if (ne.isComposing || ne.inputType === 'insertCompositionText' || ne.inputType === 'insertFromComposition') {
            if (!composingRef.current) e.currentTarget.value = ''
            return
          }
          const data = ne.data ?? e.currentTarget.value
          if (!composingRef.current && data) sendText(data)
          if (!composingRef.current) e.currentTarget.value = ''
        }}
        onKeyDown={(e) => {
          // ponytail: デスクトップのキーボード前提。スマホのソフトキーボードの Backspace(key 'Unidentified')は送れない
          // Safari は compositionend の後に確定の keydown(keyCode 229)を出す。IME の Enter を端末へ送らない
          if (SPECIAL_KEYS.has(e.key) && !e.nativeEvent.isComposing && e.keyCode !== 229) {
            e.preventDefault()
            send({ type: 'key', key: e.key })
          }
        }}
      />
    </div>
  )
}
