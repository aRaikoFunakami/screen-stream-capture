# react-android-screen

React components for Android screen streaming

## Features

- 🎥 H.264 video streaming via WebSocket
- ⚡ Low latency with JMuxer
- 🔁 Device rotation / resolution change supported (auto reset + layout follow)
- 🖼️ Video fit control (`contain` / `cover`)
- 🔄 Auto-reconnect support
- 🕒 Live latency catch-up (optional)
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
      fit="contain"
      maxHeight="70vh"
      // ライブ視聴用途: 遅延が溜まったら自動で追従（デフォルト true）
      liveSync
      // 遅延が 1.5s を超えたら、末尾 - 0.3s に追従する（ms）
      maxLatencyMs={1500}
      targetLatencyMs={300}
      onConnected={() => console.log('Connected!')}
      onError={(error) => console.error('Error:', error)}
    />
  )
}
```

Notes:

- Device rotation / resolution change is handled internally. Consumers typically do not need to add any special code.
- Layout is responsive to the stream aspect ratio; if your grid/cards show extra whitespace after rotation, adjust the app-side layout (CSS/grid rules).

### RemoteControlLayer（端末の操作）

`H264Player` の children に置くと、映像の上でのクリック/タップ・ドラッグ・ホイール・キー入力・文字（IME 確定・貼り付けを含む）を操作用 WebSocket（backend の `WS /api/ws/control/{serial}`）へ送る。座標は object-fit の余白を除いた映像領域に対する 0..1。

```tsx
const [video, setVideo] = useState<HTMLVideoElement | null>(null)

<H264Player wsUrl="/api/ws/stream/emulator-5554" onVideoRef={(r) => setVideo(r.current)}>
  <RemoteControlLayer
    controlUrl="/api/ws/control/emulator-5554"   // 認可済みの中継先を指定する
    authToken={token}                             // 接続直後の auth メッセージで送る（URL には載せない）
    videoEl={video}
    onStatus={(s, detail) => console.log(s, detail)}  // 'connecting' | 'ready' | 'closed' | 'error'
  />
</H264Player>
```

- `ready` を受けるまで入力は送らない。個々のメッセージの失敗は `onStatus('error', detail)` で知らせ、接続は使い続ける。
- 長い文字列は 256 文字ずつに分けて送る。

### useAndroidStream Hook

For more control, use the custom hook:

```tsx
import { useAndroidStream } from 'react-android-screen'

function CustomPlayer() {
  const { videoRef, status, stats, connect, disconnect } = useAndroidStream({
    wsUrl: '/api/ws/stream/emulator-5554',
    autoConnect: true,
    fps: 30,
    // ライブ視聴用途: 遅延が溜まったら自動で追従（デフォルト true）
    liveSync: true,
    maxLatencyMs: 1500,
    targetLatencyMs: 300,
    // 解像度変更（回転）を検出した時に呼ばれる（JMuxer リセット完了後）
    onResolutionChange: () => {
      const video = videoRef.current
      if (video?.videoWidth && video?.videoHeight) {
        video.style.aspectRatio = `${video.videoWidth} / ${video.videoHeight}`
      }
    },
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

## Live Sync (遅延追従) 仕様

### 目的

H.264 ライブ配信をブラウザで再生していると、端末側は画面が切り替わっているのに、ブラウザの再生が過去に取り残される（遅延が増え続ける）場合がある。

本機能は、MSE の再生バッファが溜まりすぎた場合に「過去フレームを捨てて、最新に追従」することで、ライブ視聴としての体感遅延を上限化する。

### 用語

- `currentTime`: HTMLVideoElement の現在再生時刻（秒）
- `bufferedEnd`: `video.buffered` の最後のレンジの終端（秒）
- $latencySec = bufferedEnd - currentTime$

### 入力パラメータ

- `liveSync` (`boolean`, default: `true`)
  - `true`: 遅延追従を有効化
  - `false`: 遅延追従を無効化（溜まったバッファは捨てない）
- `maxLatencyMs` (`number`, default: `1500`)
  - 追従を発動する遅延閾値（ms）
- `targetLatencyMs` (`number`, default: `300`)
  - 追従後に狙う遅延（ms）

#### Stall Recovery（固まり検知と自動復旧）

- `stallRecovery` (`boolean`, default: `true`)
  - `true`: 固まり検知と自動復旧を有効化
  - `false`: 無効化（固まり時に自動で復旧しない）
- `stallTimeoutMs` (`number`, default: `2000`)
  - 固まり判定のしきい値（ms）
  - 「`timeupdate` に相当する再生進捗（`currentTime` 増加）がこの時間以上観測できない」場合に固まりとみなす
- `maxRecoveries` (`number`, default: `3`)
  - 自動復旧の最大回数（無限ループ防止）
- `recoveryCooldownMs` (`number`, default: `1000`)
  - 復旧試行の最小間隔（暴走防止）

### 仕様（アルゴリズム）

#### 追従判定

- `liveSync === true` のときのみ動作する。
- `video.readyState >= 2` かつ `video.buffered.length > 0` のときのみ判定する。
- $latencySec \le maxLatencyMs/1000$ の場合は何もしない。
- $latencySec > maxLatencyMs/1000$ の場合、追従シークを試みる。

#### 追従シーク

- 追従先は次の通り。

  $$seekTo = bufferedEnd - (targetLatencyMs/1000)$$

- `seekTo` は `0` 未満にならないようにクランプする。
- 追従は高頻度に行わず、最短 250ms 以上空ける（スロットル）。
- 判定は 500ms 間隔のタイマーでも行い、受信が止まり気味でも遅延補正が働くようにする。

### 期待する動作

- 通常（遅延が小さい）: シークは発生せず、映像は連続再生される。
- 一時的に処理落ち等で遅延が溜まる: 一定以上溜まったタイミングで `seek` が発生し、再生位置が最新付近へ戻る。

### トレードオフ / 非目標

- 追従時は「過去フレームを捨てる」ため、一瞬映像が飛んだように見えることがある（ライブ用途では許容）。
- 録画/巻き戻しなどの「完全な時系列再生」は非目標。

### 安全性（黒画面/固まりの回避方針）

- `video.buffered` が空のときはシークしない（範囲外ジャンプを避ける）。
- `seek` 例外は `console.warn` に出し、再生を継続する。

注意: H.264 の復号は任意点から常に即時再開できるとは限らない（IDR を待つ場合がある）。そのため、固まりを完全にゼロにはできない。

（将来拡張案）固まり検知（stalled/waiting + timeupdate 無進行）→ JMuxer リセットで次の IDR から復旧、を追加可能。

### Stall Recovery 仕様

#### 固まり判定

- `stallRecovery === true` のときのみ動作する。
- `video.paused` または `video.ended` のときは固まり判定しない。
- 受信開始直後の誤検知を避けるため、一定数の受信チャンク（目安: 3 以上）を受け取るまで判定しない。
- $nowMs - lastPlaybackProgressAtMs > stallTimeoutMs$ の場合に固まりとみなす。

#### 復旧アクション

固まりと判定した場合、次の順で段階的に復旧を試みる（上限: `maxRecoveries`、間隔: `recoveryCooldownMs`）。

1) **seek**: buffered の末尾付近へシーク（`targetLatencyMs` を目安）
2) **jmuxer reset**: JMuxer/MediaSource を作り直し、次のフレームから復旧を試みる
3) **reconnect**: WebSocket を張り直して再接続を試みる

上限に達した場合は `onError('Playback stalled (recovery limit reached)')` を呼び、ステータスを `error` とする。

## API

### H264PlayerProps

| Prop | Type | Default | Description |
| ---- | ---- | ------- | ----------- |
| `wsUrl` | `string` | required | WebSocket URL for the stream |
| `className` | `string` | `''` | CSS class name |
| `videoClassName` | `string` | `''` | CSS class name for the `<video>` element |
| `videoStyle` | `React.CSSProperties` | - | Inline style for the `<video>` element |
| `fit` | `'contain' \| 'cover'` | `'contain'` | `object-fit` behavior for the video |
| `maxHeight` | `string` | `'70vh'` | Max height for the video (CSS length) |
| `fps` | `number` | `30` | Frame rate for JMuxer |
| `liveSync` | `boolean` | `true` | Catch up when playback latency grows |
| `maxLatencyMs` | `number` | `1500` | Threshold to trigger catch-up (ms) |
| `targetLatencyMs` | `number` | `300` | Desired latency after catch-up (ms) |
| `stallRecovery` | `boolean` | `true` | Enable stall detection and recovery |
| `stallTimeoutMs` | `number` | `2000` | Stall detection threshold (ms) |
| `maxRecoveries` | `number` | `3` | Max recovery attempts |
| `recoveryCooldownMs` | `number` | `1000` | Min interval between recoveries (ms) |
| `debug` | `boolean` | `false` | Enable debug logs to console |
| `autoReconnect` | `boolean` | `true` | Auto-reconnect on disconnect |
| `reconnectInterval` | `number` | `3000` | Reconnect interval (ms) |
| `onConnected` | `() => void` | - | Called when connected |
| `onDisconnected` | `() => void` | - | Called when disconnected |
| `onError` | `(error: string) => void` | - | Called on error |

### useAndroidStreamOptions

| Option | Type | Default | Description |
| ------ | ---- | ------- | ----------- |
| `wsUrl` | `string` | required | WebSocket URL |
| `autoConnect` | `boolean` | `true` | Connect automatically |
| `fps` | `number` | `30` | Frame rate for JMuxer |
| `liveSync` | `boolean` | `true` | Catch up when playback latency grows |
| `maxLatencyMs` | `number` | `1500` | Threshold to trigger catch-up (ms) |
| `targetLatencyMs` | `number` | `300` | Desired latency after catch-up (ms) |
| `stallRecovery` | `boolean` | `true` | Enable stall detection and recovery |
| `stallTimeoutMs` | `number` | `2000` | Stall detection threshold (ms) |
| `maxRecoveries` | `number` | `3` | Max recovery attempts |
| `recoveryCooldownMs` | `number` | `1000` | Min interval between recoveries (ms) |
| `debug` | `boolean` | `false` | Enable debug logs to console |
| `onConnected` | `() => void` | - | Called when connected |
| `onDisconnected` | `() => void` | - | Called when disconnected |
| `onError` | `(error: string) => void` | - | Called on error |

## 手動検証（遅延/固まりのチューニング）

1) まず `debug: true` で起動し、`LiveSync applied` / `Playback stalled...` ログが出る条件を確認する
2) Chrome DevTools で CPU Throttling を有効化し、遅延が溜まる状況でも数秒以内に追従することを確認する
3) タブをバックグラウンドにした場合、固まり復旧が誤発動しないことを確認する（`document.visibilityState === 'hidden'` の間は復旧を抑制）
4) 体感が「飛びすぎる」場合: `maxLatencyMs` を上げる / `targetLatencyMs` を上げる
5) 固まりが長引く場合: `stallTimeoutMs` を下げる（ただし誤検知増）/ `maxRecoveries` を増やす（ただし暴走注意）

### useAndroidStreamResult

| Property | Type | Description |
| -------- | ---- | ----------- |
| `videoRef` | `RefObject<HTMLVideoElement>` | Ref for the video element |
| `status` | `StreamStatus` | Connection status |
| `stats` | `StreamStats` | Stream statistics |
| `connect` | `() => void` | Connect to the stream |
| `disconnect` | `() => void` | Disconnect from the stream |

## License

MIT
