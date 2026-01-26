import { useEffect, useState, useRef } from 'react'
import { H264Player } from 'react-android-screen'

interface DeviceInfo {
  serial: string
  state: string
  model: string | null
  manufacturer: string | null
  isEmulator: boolean
  lastSeen: string
}

function App() {
  const [health, setHealth] = useState<{ status: string; version: string } | null>(null)
  const [devices, setDevices] = useState<DeviceInfo[]>([])
  const [error, setError] = useState<string | null>(null)
  const [sseStatus, setSseStatus] = useState<'connecting' | 'connected' | 'disconnected'>('disconnected')
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  const captureWsRef = useRef<WebSocket | null>(null)
  const [captureStatus, setCaptureStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected')
  const [captureError, setCaptureError] = useState<string | null>(null)
  const [captureQuality, setCaptureQuality] = useState<number>(80)
  const [captureSaveOnServer, setCaptureSaveOnServer] = useState<boolean>(false)
  const pendingCaptureIdRef = useRef<string | null>(null)

  useEffect(() => {
    // 初期データ取得
    fetch('/api/healthz')
      .then((res) => res.json())
      .then((data) => setHealth(data))
      .catch((err) => setError(err.message))

    // SSE 接続
    const connectSSE = () => {
      setSseStatus('connecting')
      const eventSource = new EventSource('/api/events')

      eventSource.onopen = () => {
        console.log('SSE connected')
        setSseStatus('connected')
      }

      eventSource.addEventListener('devices', (event) => {
        try {
          const data = JSON.parse(event.data)
          setDevices(data)
        } catch (err) {
          console.error('Failed to parse SSE message:', err)
        }
      })

      eventSource.onerror = () => {
        console.log('SSE disconnected')
        setSseStatus('disconnected')
        eventSource.close()
        eventSourceRef.current = null
        // 自動再接続
        setTimeout(connectSSE, 3000)
      }

      eventSourceRef.current = eventSource
    }

    connectSSE()

    return () => {
      eventSourceRef.current?.close()
    }
  }, [])

  // Capture WebSocket: keep connected while modal is open.
  useEffect(() => {
    if (!selectedDevice) {
      captureWsRef.current?.close()
      captureWsRef.current = null
      setCaptureStatus('disconnected')
      setCaptureError(null)
      pendingCaptureIdRef.current = null
      return
    }

    setCaptureStatus('connecting')
    setCaptureError(null)
    pendingCaptureIdRef.current = null

    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/api/ws/capture/${selectedDevice}`)
    ws.binaryType = 'arraybuffer'

    ws.onopen = () => {
      setCaptureStatus('connected')
    }

    ws.onclose = () => {
      setCaptureStatus('disconnected')
    }

    ws.onerror = () => {
      setCaptureError('capture WebSocket error')
    }

    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'error') {
            setCaptureError(`${msg.code ?? 'ERROR'}: ${msg.message ?? 'unknown error'}`)
            return
          }
          if (msg.type === 'capture_result') {
            pendingCaptureIdRef.current = msg.capture_id
            return
          }
        } catch (e) {
          console.error('Failed to parse capture message:', e)
        }
        return
      }

      // Binary (JPEG bytes)
      try {
        const buf = event.data as ArrayBuffer
        const blob = new Blob([buf], { type: 'image/jpeg' })
        const url = URL.createObjectURL(blob)

        const captureId = pendingCaptureIdRef.current ?? 'capture'
        const ts = new Date().toISOString().replace(/[:.]/g, '')
        const filename = `${selectedDevice}_${ts}_${captureId}.jpg`

        const a = document.createElement('a')
        a.href = url
        a.download = filename
        document.body.appendChild(a)
        a.click()
        a.remove()

        URL.revokeObjectURL(url)
      } catch (e) {
        console.error('Failed to handle capture binary:', e)
      } finally {
        pendingCaptureIdRef.current = null
      }
    }

    captureWsRef.current = ws

    return () => {
      ws.close()
      if (captureWsRef.current === ws) {
        captureWsRef.current = null
      }
    }
  }, [selectedDevice])

  const getStateColor = (state: string) => {
    switch (state) {
      case 'device':
        return 'bg-green-500'
      case 'offline':
        return 'bg-gray-500'
      case 'unauthorized':
        return 'bg-yellow-500'
      default:
        return 'bg-red-500'
    }
  }

  const getStateLabel = (state: string) => {
    switch (state) {
      case 'device':
        return 'オンライン'
      case 'offline':
        return 'オフライン'
      case 'unauthorized':
        return '未承認'
      default:
        return state
    }
  }

  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-blue-600 text-white p-4 shadow-lg">
        <div className="container mx-auto flex justify-between items-center">
          <h1 className="text-2xl font-bold">Screen Stream Capture</h1>
          <div className="flex items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full ${
                sseStatus === 'connected'
                  ? 'bg-green-400'
                  : sseStatus === 'connecting'
                  ? 'bg-yellow-400 animate-pulse'
                  : 'bg-red-400'
              }`}
            />
            <span className="text-sm opacity-80">
              {sseStatus === 'connected' ? 'リアルタイム接続中' : sseStatus === 'connecting' ? '接続中...' : '未接続'}
            </span>
          </div>
        </div>
      </header>

      <main className="container mx-auto p-4">
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4">システム状態</h2>

          {error && (
            <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
              エラー: {error}
            </div>
          )}

          {health ? (
            <div className="space-y-2">
              <p>
                <span className="font-medium">ステータス:</span>{' '}
                <span className={health.status === 'ok' ? 'text-green-600' : 'text-red-600'}>{health.status}</span>
              </p>
              <p>
                <span className="font-medium">バージョン:</span> {health.version}
              </p>
            </div>
          ) : (
            <p className="text-gray-500">読み込み中...</p>
          )}
        </div>

        <div className="mt-6 bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4">デバイス一覧 ({devices.length}台)</h2>

          {devices.length === 0 ? (
            <p className="text-gray-500">接続されているデバイスがありません</p>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {devices.map((device) => (
                <div
                  key={device.serial}
                  onClick={() => device.state === 'device' && setSelectedDevice(device.serial)}
                  className={`border rounded-lg p-4 transition-shadow ${
                    device.state === 'device'
                      ? 'hover:shadow-md cursor-pointer hover:border-blue-400'
                      : 'opacity-60 cursor-not-allowed'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`w-3 h-3 rounded-full ${getStateColor(device.state)}`} />
                    <span className="font-medium">
                      {device.model || device.serial}
                    </span>
                    {device.isEmulator && (
                      <span className="bg-purple-100 text-purple-800 text-xs px-2 py-0.5 rounded">
                        エミュレータ
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-gray-600 space-y-1">
                    <p>
                      <span className="font-medium">シリアル:</span> {device.serial}
                    </p>
                    {device.manufacturer && (
                      <p>
                        <span className="font-medium">メーカー:</span> {device.manufacturer}
                      </p>
                    )}
                    <p>
                      <span className="font-medium">状態:</span> {getStateLabel(device.state)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>

      {/* ストリーミングモーダル - react-android-screen の H264Player を使用 */}
      {selectedDevice && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-hidden">
            <div className="flex justify-between items-center p-4 border-b">
              <div className="flex items-center gap-4">
                <h3 className="text-lg font-semibold">{selectedDevice}</h3>
                <div className="flex items-center gap-2 text-sm">
                  <span
                    className={`w-2 h-2 rounded-full ${
                      captureStatus === 'connected'
                        ? 'bg-green-500'
                        : captureStatus === 'connecting'
                        ? 'bg-yellow-500 animate-pulse'
                        : 'bg-gray-400'
                    }`}
                  />
                  <span className="text-gray-600">
                    {captureStatus === 'connected'
                      ? 'キャプチャ接続中'
                      : captureStatus === 'connecting'
                      ? 'キャプチャ接続中...'
                      : 'キャプチャ未接続'}
                  </span>
                </div>
              </div>
              <button
                onClick={() => setSelectedDevice(null)}
                className="text-gray-500 hover:text-gray-700 text-2xl"
              >
                ×
              </button>
            </div>
            <div className="p-4">
              {captureError && (
                <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
                  キャプチャエラー: {captureError}
                </div>
              )}

              <div className="flex flex-wrap items-center gap-4 mb-4">
                <button
                  onClick={() => {
                    const ws = captureWsRef.current
                    if (!ws || ws.readyState !== WebSocket.OPEN) {
                      setCaptureError('capture WebSocket is not connected')
                      return
                    }
                    setCaptureError(null)
                    ws.send(
                      JSON.stringify({
                        type: 'capture',
                        format: 'jpeg',
                        quality: captureQuality,
                        save: captureSaveOnServer,
                      })
                    )
                  }}
                  disabled={captureStatus !== 'connected'}
                  className={`px-4 py-2 rounded text-white ${
                    captureStatus === 'connected' ? 'bg-blue-600 hover:bg-blue-700' : 'bg-gray-400 cursor-not-allowed'
                  }`}
                >
                  キャプチャ（JPEG）
                </button>

                <label className="flex items-center gap-2 text-sm text-gray-700">
                  <span>品質</span>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={captureQuality}
                    onChange={(e) => setCaptureQuality(Number(e.target.value))}
                    className="border rounded px-2 py-1 w-20"
                  />
                </label>

                <label className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={captureSaveOnServer}
                    onChange={(e) => setCaptureSaveOnServer(e.target.checked)}
                  />
                  サーバーにも保存
                </label>
              </div>

              <H264Player
                wsUrl={`/api/ws/stream/${selectedDevice}`}
                className="w-full"
                onError={(error: string) => console.error('Player error:', error)}
                onConnected={() => console.log('Stream connected')}
                onDisconnected={() => console.log('Stream disconnected')}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
