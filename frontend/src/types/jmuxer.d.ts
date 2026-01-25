declare module 'jmuxer' {
  interface JMuxerOptions {
    node: HTMLVideoElement | string
    mode?: 'video' | 'audio' | 'both'
    fps?: number
    flushingTime?: number
    clearBuffer?: boolean
    debug?: boolean
    onReady?: () => void
    onError?: (error: Error) => void
  }

  interface FeedData {
    video?: Uint8Array
    audio?: Uint8Array
    duration?: number
  }

  export default class JMuxer {
    constructor(options: JMuxerOptions)
    feed(data: FeedData): void
    destroy(): void
  }
}
