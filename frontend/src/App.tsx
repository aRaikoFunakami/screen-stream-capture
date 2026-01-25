import { useEffect, useState, useRef } from 'react'

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

  useEffect(() => {
    // 初期データ取得
    fetch('/healthz')
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
                  className="border rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer"
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
    </div>
  )
}

export default App
