import { useEffect, useState, useRef } from 'react'
import { StreamCard } from './components/StreamCard'

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
  const eventSourceRef = useRef<EventSource | null>(null)

  // Capture settings (global)
  const [captureQuality, setCaptureQuality] = useState<number>(80)
  const [captureSaveOnServer, setCaptureSaveOnServer] = useState<boolean>(false)

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

  // Filter online devices for streaming
  const onlineDevices = devices.filter((d) => d.state === 'device')
  const offlineDevices = devices.filter((d) => d.state !== 'device')

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

      <main className="container mx-auto p-4 space-y-6">
        {/* システム状態 */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4 text-gray-900">システム状態</h2>

          {error && (
            <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
              エラー: {error}
            </div>
          )}

          {health ? (
            <div className="space-y-2 text-gray-800">
              <p>
                <span className="font-medium text-gray-700">ステータス:</span>{' '}
                <span className={health.status === 'ok' ? 'text-green-600' : 'text-red-600'}>{health.status}</span>
              </p>
              <p>
                <span className="font-medium text-gray-700">バージョン:</span>{' '}
                <span className="text-gray-900">{health.version}</span>
              </p>
            </div>
          ) : (
            <p className="text-gray-500">読み込み中...</p>
          )}
        </div>

        {/* キャプチャ設定 */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4 text-gray-900">キャプチャ設定</h2>
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <span>品質</span>
              <input
                type="number"
                min={1}
                max={100}
                value={captureQuality}
                onChange={(e) => setCaptureQuality(Number(e.target.value))}
                className="border rounded px-2 py-1 w-20 text-gray-900"
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
        </div>

        {/* オンラインデバイス - ストリーミング表示 */}
        {onlineDevices.length > 0 && (
          <div>
            <h2 className="text-xl font-semibold mb-4 text-gray-900">
              ストリーミング ({onlineDevices.length}台)
            </h2>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {onlineDevices.map((device) => (
                <StreamCard
                  key={device.serial}
                  serial={device.serial}
                  model={device.model}
                  manufacturer={device.manufacturer}
                  isEmulator={device.isEmulator}
                  captureQuality={captureQuality}
                  captureSaveOnServer={captureSaveOnServer}
                />
              ))}
            </div>
          </div>
        )}

        {/* オフラインデバイス一覧 */}
        {offlineDevices.length > 0 && (
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4 text-gray-900">
              オフラインデバイス ({offlineDevices.length}台)
            </h2>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {offlineDevices.map((device) => (
                <div
                  key={device.serial}
                  className="border rounded-lg p-4 opacity-60"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`w-3 h-3 rounded-full ${getStateColor(device.state)}`} />
                    <span className="font-medium text-gray-900">
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
          </div>
        )}

        {/* デバイスがない場合 */}
        {devices.length === 0 && (
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4 text-gray-900">デバイス一覧</h2>
            <p className="text-gray-500">接続されているデバイスがありません</p>
          </div>
        )}
      </main>
    </div>
  )
}

export default App
