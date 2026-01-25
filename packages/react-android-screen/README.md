# react-android-screen

React components for Android screen streaming

## Features

- 🎥 H.264 video streaming via WebSocket
- ⚡ Low latency with JMuxer
- 🔄 Auto-reconnect support
- 📊 Built-in stats display
- 🎨 Customizable styling

## Installation

```bash
npm install react-android-screen
# or
yarn add react-android-screen
```

## Usage

### H264Player Component

```tsx
import { H264Player } from 'react-android-screen'

function App() {
  return (
    <H264Player
      wsUrl="/api/ws/stream/emulator-5554"
      className="w-full max-w-2xl"
      onConnected={() => console.log('Connected!')}
      onError={(error) => console.error('Error:', error)}
    />
  )
}
```

### useAndroidStream Hook

For more control, use the custom hook:

```tsx
import { useAndroidStream } from 'react-android-screen'

function CustomPlayer() {
  const { videoRef, status, stats, connect, disconnect } = useAndroidStream({
    wsUrl: '/api/ws/stream/emulator-5554',
    autoConnect: true,
    fps: 30,
  })

  return (
    <div>
      <video ref={videoRef} autoPlay muted playsInline />
      <p>Status: {status}</p>
      <p>Received: {stats.bytes} bytes</p>
      <button onClick={connect}>Connect</button>
      <button onClick={disconnect}>Disconnect</button>
    </div>
  )
}
```

## API

### H264PlayerProps

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `wsUrl` | `string` | required | WebSocket URL for the stream |
| `className` | `string` | `''` | CSS class name |
| `fps` | `number` | `30` | Frame rate for JMuxer |
| `autoReconnect` | `boolean` | `true` | Auto-reconnect on disconnect |
| `reconnectInterval` | `number` | `3000` | Reconnect interval (ms) |
| `onConnected` | `() => void` | - | Called when connected |
| `onDisconnected` | `() => void` | - | Called when disconnected |
| `onError` | `(error: string) => void` | - | Called on error |

### useAndroidStreamOptions

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `wsUrl` | `string` | required | WebSocket URL |
| `autoConnect` | `boolean` | `true` | Connect automatically |
| `fps` | `number` | `30` | Frame rate for JMuxer |
| `onConnected` | `() => void` | - | Called when connected |
| `onDisconnected` | `() => void` | - | Called when disconnected |
| `onError` | `(error: string) => void` | - | Called on error |

### useAndroidStreamResult

| Property | Type | Description |
|----------|------|-------------|
| `videoRef` | `RefObject<HTMLVideoElement>` | Ref for the video element |
| `status` | `StreamStatus` | Connection status |
| `stats` | `StreamStats` | Stream statistics |
| `connect` | `() => void` | Connect to the stream |
| `disconnect` | `() => void` | Disconnect from the stream |

## License

MIT
