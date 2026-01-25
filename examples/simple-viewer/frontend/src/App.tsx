import { useState } from 'react'
import { H264Player } from 'react-android-screen'

function App() {
  const [serial, setSerial] = useState('emulator-5554')
  const [isStreaming, setIsStreaming] = useState(false)

  return (
    <div className="min-h-screen p-8">
      <h1 className="text-3xl font-bold mb-8 text-center">
        Android Screen Viewer
      </h1>

      <div className="max-w-4xl mx-auto">
        {/* デバイス選択 */}
        <div className="mb-6 flex gap-4 items-center">
          <label className="text-gray-400">Device Serial:</label>
          <input
            type="text"
            value={serial}
            onChange={(e) => setSerial(e.target.value)}
            className="bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
            placeholder="emulator-5554"
          />
          <button
            onClick={() => setIsStreaming(!isStreaming)}
            className={`px-4 py-2 rounded transition-colors ${
              isStreaming
                ? 'bg-red-600 hover:bg-red-700'
                : 'bg-green-600 hover:bg-green-700'
            }`}
          >
            {isStreaming ? 'Stop' : 'Start'}
          </button>
        </div>

        {/* プレイヤー */}
        {isStreaming && (
          <H264Player
            wsUrl={`/api/ws/stream/${serial}`}
            className="w-full"
            onConnected={() => console.log('Connected!')}
            onDisconnected={() => console.log('Disconnected')}
            onError={(error) => console.error('Error:', error)}
          />
        )}

        {/* 説明 */}
        {!isStreaming && (
          <div className="bg-gray-800 rounded-lg p-8 text-center">
            <p className="text-gray-400 mb-4">
              Android デバイスのシリアル番号を入力して Start をクリック
            </p>
            <p className="text-gray-500 text-sm">
              デバイスが adb に接続されていることを確認してください
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

export default App
