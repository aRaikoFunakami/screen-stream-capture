import { useEffect, useState, useRef, useCallback } from 'react'
import { H264Player } from 'react-android-screen'

interface StreamCardProps {
  serial: string
  model: string | null
  manufacturer: string | null
  isEmulator: boolean
  captureQuality?: number
  captureSaveOnServer?: boolean
}

export function StreamCard({
  serial,
  model,
  manufacturer,
  isEmulator,
  captureQuality = 80,
  captureSaveOnServer = false,
}: StreamCardProps) {
  const [captureStatus, setCaptureStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected')
  const [captureError, setCaptureError] = useState<string | null>(null)
  const [captureImageUrl, setCaptureImageUrl] = useState<string | null>(null)
  const captureWsRef = useRef<WebSocket | null>(null)
  const pendingCaptureIdRef = useRef<string | null>(null)

  // Capture WebSocket connection
  useEffect(() => {
    setCaptureStatus('connecting')
    setCaptureError(null)
    pendingCaptureIdRef.current = null

    // Delay capture WS connection to allow stream WS to establish first
    const timeoutId = setTimeout(() => {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${window.location.host}/api/ws/capture/${serial}`)
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

        // Binary (JPEG bytes) - display as overlay instead of download
        try {
          const buf = event.data as ArrayBuffer
          const blob = new Blob([buf], { type: 'image/jpeg' })
          
          // Revoke previous URL if exists
          if (captureImageUrl) {
            URL.revokeObjectURL(captureImageUrl)
          }
          
          const url = URL.createObjectURL(blob)
          setCaptureImageUrl(url)
        } catch (e) {
          console.error('Failed to handle capture binary:', e)
        } finally {
          pendingCaptureIdRef.current = null
        }
      }

      captureWsRef.current = ws
    }, 3000) // Wait 3 seconds for stream WS to establish

    return () => {
      clearTimeout(timeoutId)
      captureWsRef.current?.close()
      captureWsRef.current = null
      // Clean up capture image URL
      if (captureImageUrl) {
        URL.revokeObjectURL(captureImageUrl)
      }
    }
  }, [serial])

  const handleCapture = useCallback(() => {
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
  }, [captureQuality, captureSaveOnServer])

  const handleCloseCaptureOverlay = useCallback(() => {
    if (captureImageUrl) {
      URL.revokeObjectURL(captureImageUrl)
      setCaptureImageUrl(null)
    }
  }, [captureImageUrl])

  return (
    <div className="bg-white rounded-lg shadow p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full bg-green-500" />
          <span className="font-medium text-gray-900">
            {model || serial}
          </span>
          {isEmulator && (
            <span className="bg-purple-100 text-purple-800 text-xs px-2 py-0.5 rounded">
              エミュレータ
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span
            className={`w-2 h-2 rounded-full ${
              captureStatus === 'connected'
                ? 'bg-green-500'
                : captureStatus === 'connecting'
                ? 'bg-yellow-500 animate-pulse'
                : 'bg-gray-400'
            }`}
          />
          <span className="text-gray-500">
            {captureStatus === 'connected'
              ? 'キャプチャ可'
              : captureStatus === 'connecting'
              ? '接続中...'
              : '未接続'}
          </span>
        </div>
      </div>

      {/* Info */}
      <div className="text-xs text-gray-500 mb-2">
        <span>{serial}</span>
        {manufacturer && <span className="ml-2">({manufacturer})</span>}
      </div>

      {/* Capture button */}
      <div className="mb-3">
        <button
          onClick={handleCapture}
          disabled={captureStatus !== 'connected'}
          className={`px-3 py-1.5 rounded text-sm text-white ${
            captureStatus === 'connected'
              ? 'bg-blue-600 hover:bg-blue-700'
              : 'bg-gray-400 cursor-not-allowed'
          }`}
        >
          📷 キャプチャ
        </button>
        {captureError && (
          <span className="ml-2 text-xs text-red-600">{captureError}</span>
        )}
      </div>

      {/* Streaming area with capture overlay */}
      <div className="relative bg-black rounded overflow-hidden" style={{ aspectRatio: '9/16', maxHeight: '400px' }}>
        <H264Player
          wsUrl={`/api/ws/stream/${serial}`}
          className="w-full h-full object-contain"
          onError={(error: string) => console.error('Player error:', error)}
          onConnected={() => console.log(`Stream connected: ${serial}`)}
          onDisconnected={() => console.log(`Stream disconnected: ${serial}`)}
        />

        {/* Capture image overlay */}
        {captureImageUrl && (
          <div className="absolute inset-0 bg-black/80 flex items-center justify-center">
            <div className="relative max-w-full max-h-full">
              <img
                src={captureImageUrl}
                alt="Capture"
                className="max-w-full max-h-full object-contain"
              />
              <button
                onClick={handleCloseCaptureOverlay}
                className="absolute top-2 right-2 w-8 h-8 bg-black/50 hover:bg-black/70 text-white rounded-full flex items-center justify-center text-xl"
              >
                ×
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
