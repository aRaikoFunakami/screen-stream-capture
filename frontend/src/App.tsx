import { useEffect, useState } from 'react'

function App() {
  const [health, setHealth] = useState<{ status: string; version: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/devices')
      .then((res) => res.json())
      .then((data) => console.log('Devices:', data))
      .catch((err) => console.error('Failed to fetch devices:', err))

    fetch('/healthz')
      .then((res) => res.json())
      .then((data) => setHealth(data))
      .catch((err) => setError(err.message))
  }, [])

  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-blue-600 text-white p-4 shadow-lg">
        <h1 className="text-2xl font-bold">Screen Stream Capture</h1>
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
                <span className={health.status === 'ok' ? 'text-green-600' : 'text-red-600'}>
                  {health.status}
                </span>
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
          <h2 className="text-xl font-semibold mb-4">デバイス一覧</h2>
          <p className="text-gray-500">接続されているデバイスがありません</p>
        </div>
      </main>
    </div>
  )
}

export default App
