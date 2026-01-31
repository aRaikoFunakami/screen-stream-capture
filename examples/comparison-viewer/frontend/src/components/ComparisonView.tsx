import { H264Player, WebCodecsPlayer, isWebCodecsSupported } from 'react-android-screen'

interface Device {
  serial: string
  state: string
  model: string | null
  manufacturer: string | null
}

interface ComparisonViewProps {
  device: Device
}

export function ComparisonView({ device }: ComparisonViewProps) {
  const wsUrl = `/api/ws/stream/${device.serial}`

  return (
    <div className="flex flex-col h-full">
      {/* デバイス情報ヘッダー */}
      <div className="bg-gray-800 rounded-lg p-4 mb-4">
        <div className="flex items-center gap-3">
          <span className="w-3 h-3 rounded-full bg-green-500" />
          <div>
            <h2 className="font-bold text-lg">
              {device.model || device.serial}
            </h2>
            <p className="text-sm text-gray-400">
              {device.serial}
              {device.manufacturer && ` • ${device.manufacturer}`}
            </p>
          </div>
        </div>
      </div>

      {/* プレイヤー比較 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 flex-1">
        {/* MSE/JMuxer プレイヤー */}
        <div className="flex flex-col bg-gray-800 rounded-lg overflow-hidden">
          <div className="bg-blue-600 px-4 py-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="font-semibold">MSE / JMuxer</span>
              <span className="text-xs bg-blue-700 px-2 py-0.5 rounded">
                flushingTime: 10ms
              </span>
            </div>
            <span className="text-xs text-blue-200">バランス型</span>
          </div>
          <div className="flex-1 p-4 flex items-center justify-center bg-black overflow-hidden">
            <H264Player
              wsUrl={wsUrl}
              className="max-w-full max-h-full"
              maxHeight="50vh"
              onConnected={() => console.log('[MSE] Connected')}
              onDisconnected={() => console.log('[MSE] Disconnected')}
              onError={(e) => console.error('[MSE] Error:', e)}
            />
          </div>
          <div className="px-4 py-2 text-xs text-gray-400 border-t border-gray-700">
            <p>• MediaSource Extensions + JMuxer</p>
            <p>• 期待レイテンシ: 25-100ms</p>
            <p>• ブラウザ互換性: 高</p>
          </div>
        </div>

        {/* WebCodecs プレイヤー */}
        <div className="flex flex-col bg-gray-800 rounded-lg overflow-hidden">
          <div className="bg-purple-600 px-4 py-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="font-semibold">WebCodecs</span>
              <span className="text-xs bg-purple-700 px-2 py-0.5 rounded">
                VideoDecoder + Canvas
              </span>
            </div>
            <span className="text-xs text-purple-200">低レイテンシ</span>
          </div>
          <div className="flex-1 p-4 flex items-center justify-center bg-black overflow-hidden">
            {isWebCodecsSupported() ? (
              <WebCodecsPlayer
                wsUrl={wsUrl}
                className="max-w-full max-h-full"
                canvasClassName="max-w-full max-h-full"
                canvasStyle={{ maxHeight: '50vh' }}
                onConnected={() => console.log('[WebCodecs] Connected')}
                onDisconnected={() => console.log('[WebCodecs] Disconnected')}
                onError={(e) => console.error('[WebCodecs] Error:', e)}
              />
            ) : (
              <div className="text-center text-gray-500 p-8">
                <p className="text-lg mb-2">⚠️ WebCodecs 非対応</p>
                <p className="text-sm">
                  このブラウザは WebCodecs API に対応していません。
                </p>
                <p className="text-sm">
                  Chrome または Edge をご使用ください。
                </p>
              </div>
            )}
          </div>
          <div className="px-4 py-2 text-xs text-gray-400 border-t border-gray-700">
            <p>• VideoDecoder + Canvas 直接描画</p>
            <p>• 期待レイテンシ: &lt;10ms</p>
            <p>• ブラウザ互換性: Chrome/Edge のみ</p>
          </div>
        </div>
      </div>

      {/* 説明 */}
      <div className="mt-4 bg-gray-800/50 rounded-lg p-4 text-sm text-gray-400">
        <p>
          <strong className="text-gray-300">比較のポイント:</strong>{' '}
          両方のプレイヤーで同じデバイスのストリームを同時に表示しています。
          画面を動かした時の反映速度の違いを比較してください。
        </p>
        <p className="mt-2">
          <strong className="text-gray-300">注意:</strong>{' '}
          WebCodecs は Chrome/Edge のみ対応です。Safari や Firefox では MSE のみ使用してください。
        </p>
      </div>
    </div>
  )
}
