import { useState } from 'react'
import { DeviceSelector } from './components/DeviceSelector'
import { ComparisonView } from './components/ComparisonView'

interface Device {
  serial: string
  state: string
  model: string | null
  manufacturer: string | null
}

export default function App() {
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null)

  return (
    <div className="min-h-screen p-4">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-center">
          MSE vs WebCodecs 比較ビューアー
        </h1>
        <p className="text-center text-gray-400 mt-1">
          H.264 ストリーミングの遅延を視覚的に比較
        </p>
      </header>

      <div className="max-w-7xl mx-auto">
        <DeviceSelector
          selectedSerial={selectedDevice?.serial ?? null}
          onSelect={setSelectedDevice}
        />

        {selectedDevice ? (
          <ComparisonView device={selectedDevice} />
        ) : (
          <div className="text-center text-gray-500 mt-12">
            <p className="text-lg">デバイスを選択してください</p>
            <p className="text-sm mt-2">
              接続された Android デバイスまたはエミュレータが自動的に検出されます
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
