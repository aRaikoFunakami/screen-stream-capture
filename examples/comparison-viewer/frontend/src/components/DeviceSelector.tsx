import { useEffect, useState } from 'react'

interface Device {
  serial: string
  state: string
  model: string | null
  manufacturer: string | null
}

interface DeviceSelectorProps {
  selectedSerial: string | null
  onSelect: (device: Device | null) => void
}

export function DeviceSelector({ selectedSerial, onSelect }: DeviceSelectorProps) {
  const [devices, setDevices] = useState<Device[]>([])
  const [isConnected, setIsConnected] = useState(false)

  useEffect(() => {
    // SSE でデバイス一覧を監視
    const eventSource = new EventSource('/api/sse/devices')

    eventSource.onopen = () => {
      console.log('SSE connected')
      setIsConnected(true)
    }

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'devices') {
          // state が 'device' のもののみ（オンライン状態）
          const onlineDevices = data.devices.filter(
            (d: Device) => d.state === 'device'
          )
          setDevices(onlineDevices)

          // 選択中のデバイスが消えた場合は選択解除
          if (selectedSerial && !onlineDevices.find((d: Device) => d.serial === selectedSerial)) {
            onSelect(null)
          }
        }
      } catch (e) {
        console.error('Failed to parse SSE message:', e)
      }
    }

    eventSource.onerror = () => {
      console.error('SSE connection error')
      setIsConnected(false)
    }

    return () => {
      eventSource.close()
    }
  }, [selectedSerial, onSelect])

  const handleSelect = (serial: string) => {
    const device = devices.find((d) => d.serial === serial) ?? null
    onSelect(device)
  }

  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-2">
        <label className="text-sm font-medium text-gray-300">
          デバイス選択
        </label>
        <div className="flex items-center gap-2 text-xs">
          <span
            className={`w-2 h-2 rounded-full ${
              isConnected ? 'bg-green-500' : 'bg-red-500'
            }`}
          />
          <span className="text-gray-400">
            {isConnected ? 'デバイス監視中' : '接続中...'}
          </span>
        </div>
      </div>

      {devices.length === 0 ? (
        <div className="bg-gray-800 rounded-lg p-4 text-center text-gray-500">
          <p>接続されているデバイスがありません</p>
          <p className="text-xs mt-1">
            Android デバイスまたはエミュレータを接続してください
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {devices.map((device) => (
            <button
              key={device.serial}
              onClick={() => handleSelect(device.serial)}
              className={`p-4 rounded-lg border-2 transition-all text-left ${
                selectedSerial === device.serial
                  ? 'border-blue-500 bg-blue-900/30'
                  : 'border-gray-700 bg-gray-800 hover:border-gray-600'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="w-2 h-2 rounded-full bg-green-500" />
                <span className="font-medium truncate">
                  {device.model || device.serial}
                </span>
              </div>
              <div className="text-xs text-gray-400 truncate">
                {device.serial}
              </div>
              {device.manufacturer && (
                <div className="text-xs text-gray-500 mt-1">
                  {device.manufacturer}
                </div>
              )}
              {device.serial.startsWith('emulator') && (
                <span className="inline-block mt-2 text-xs bg-purple-600/50 text-purple-200 px-2 py-0.5 rounded">
                  エミュレータ
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
