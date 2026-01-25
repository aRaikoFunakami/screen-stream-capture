import { useEffect, useRef, useState, useCallback } from 'react'

interface VideoPlayerProps {
  serial: string
  onClose: () => void
}

type StreamStatus = 'idle' | 'connecting' | 'buffering' | 'playing' | 'error'

export function VideoPlayer({ serial, onClose }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const mediaSourceRef = useRef<MediaSource | null>(null)
  const sourceBufferRef = useRef<SourceBuffer | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const pendingBuffersRef = useRef<ArrayBuffer[]>([])

  const [status, setStatus] = useState<StreamStatus>('idle')
  const [error, setError] = useState<string | null>(null)

  const appendNextBuffer = useCallback(() => {
    const sourceBuffer = sourceBufferRef.current
    if (!sourceBuffer || sourceBuffer.updating || pendingBuffersRef.current.length === 0) {
      return
    }

    const buffer = pendingBuffersRef.current.shift()
    if (buffer) {
      try {
        sourceBuffer.appendBuffer(buffer)
      } catch (e) {
        console.error('Failed to append buffer:', e)
        setError('バッファ追加エラー')
        setStatus('error')
      }
    }
  }, [])

  const startStream = useCallback(async () => {
    if (!videoRef.current) return

    setStatus('connecting')
    setError(null)

    // MediaSource のサポートチェック
    if (!('MediaSource' in window)) {
      setError('お使いのブラウザは MediaSource API をサポートしていません')
      setStatus('error')
      return
    }

    // 既存の接続をクリーンアップ
    abortControllerRef.current?.abort()
    abortControllerRef.current = new AbortController()

    const mediaSource = new MediaSource()
    mediaSourceRef.current = mediaSource
    videoRef.current.src = URL.createObjectURL(mediaSource)

    mediaSource.addEventListener('sourceopen', async () => {
      try {
        // fMP4 (H.264) のMIMEタイプ
        const mimeType = 'video/mp4; codecs="avc1.640016"'
        
        if (!MediaSource.isTypeSupported(mimeType)) {
          throw new Error(`MIMEタイプがサポートされていません: ${mimeType}`)
        }

        const sourceBuffer = mediaSource.addSourceBuffer(mimeType)
        sourceBufferRef.current = sourceBuffer

        sourceBuffer.addEventListener('updateend', appendNextBuffer)
        sourceBuffer.addEventListener('error', () => {
          console.error('SourceBuffer error')
          setError('SourceBuffer エラー')
          setStatus('error')
        })

        setStatus('buffering')

        // ストリーム取得開始
        const response = await fetch(`/api/stream/${serial}`, {
          signal: abortControllerRef.current?.signal,
        })

        if (!response.ok) {
          throw new Error(`ストリーム取得失敗: ${response.status}`)
        }

        const reader = response.body?.getReader()
        if (!reader) {
          throw new Error('ReadableStream が利用できません')
        }

        // データを読み取り
        while (true) {
          const { done, value } = await reader.read()
          
          if (done) {
            console.log('Stream ended')
            if (mediaSource.readyState === 'open') {
              mediaSource.endOfStream()
            }
            break
          }

          if (value) {
            pendingBuffersRef.current.push(value.buffer)
            appendNextBuffer()

            // 最初のチャンク到着時に即座に再生開始
            if (videoRef.current?.paused && pendingBuffersRef.current.length <= 1) {
              try {
                videoRef.current.play()
                setStatus('playing')
              } catch (e) {
                console.warn('Auto-play blocked:', e)
              }
            }
          }
        }
      } catch (e) {
        if (e instanceof Error && e.name === 'AbortError') {
          console.log('Stream aborted')
          return
        }
        console.error('Stream error:', e)
        setError(e instanceof Error ? e.message : 'ストリームエラー')
        setStatus('error')
      }
    })

    mediaSource.addEventListener('sourceended', () => {
      console.log('MediaSource ended')
    })

    mediaSource.addEventListener('sourceclose', () => {
      console.log('MediaSource closed')
    })
  }, [serial, appendNextBuffer, status])

  const stopStream = useCallback(() => {
    abortControllerRef.current?.abort()
    
    if (sourceBufferRef.current) {
      sourceBufferRef.current.removeEventListener('updateend', appendNextBuffer)
    }

    if (mediaSourceRef.current?.readyState === 'open') {
      try {
        mediaSourceRef.current.endOfStream()
      } catch (e) {
        console.warn('Failed to end stream:', e)
      }
    }

    if (videoRef.current?.src) {
      URL.revokeObjectURL(videoRef.current.src)
      videoRef.current.src = ''
    }

    pendingBuffersRef.current = []
    setStatus('idle')
  }, [appendNextBuffer])

  useEffect(() => {
    startStream()
    return () => stopStream()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const getStatusLabel = () => {
    switch (status) {
      case 'connecting':
        return '接続中...'
      case 'buffering':
        return 'バッファリング中...'
      case 'playing':
        return '再生中'
      case 'error':
        return 'エラー'
      default:
        return '停止中'
    }
  }

  const getStatusColor = () => {
    switch (status) {
      case 'connecting':
      case 'buffering':
        return 'text-yellow-500'
      case 'playing':
        return 'text-green-500'
      case 'error':
        return 'text-red-500'
      default:
        return 'text-gray-500'
    }
  }

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full mx-4 overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b">
          <div className="flex items-center gap-3">
            <h3 className="text-lg font-semibold">デバイス: {serial}</h3>
            <span className={`text-sm ${getStatusColor()}`}>
              {getStatusLabel()}
            </span>
          </div>
          <button
            onClick={() => {
              stopStream()
              onClose()
            }}
            className="text-gray-500 hover:text-gray-700 text-2xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="bg-black aspect-video relative">
          <video
            ref={videoRef}
            className="w-full h-full"
            autoPlay
            muted
            playsInline
          />
          
          {status === 'connecting' && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-white text-center">
                <div className="animate-spin w-12 h-12 border-4 border-white border-t-transparent rounded-full mx-auto mb-4" />
                <p>デバイスに接続中...</p>
                <p className="text-sm text-gray-400 mt-2">
                  初回接続には10〜30秒かかる場合があります
                </p>
              </div>
            </div>
          )}

          {status === 'buffering' && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-white text-center">
                <div className="animate-pulse text-4xl mb-2">⏳</div>
                <p>バッファリング中...</p>
              </div>
            </div>
          )}

          {status === 'error' && error && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-white text-center">
                <div className="text-4xl mb-2">❌</div>
                <p className="text-red-400">{error}</p>
                <button
                  onClick={startStream}
                  className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-white"
                >
                  再接続
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="p-4 flex justify-between items-center">
          <div className="text-sm text-gray-600">
            {status === 'playing' && 'ライブストリーミング中'}
          </div>
          <div className="flex gap-2">
            {status === 'playing' ? (
              <button
                onClick={stopStream}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded text-white"
              >
                停止
              </button>
            ) : status !== 'connecting' && status !== 'buffering' ? (
              <button
                onClick={startStream}
                className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded text-white"
              >
                開始
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
