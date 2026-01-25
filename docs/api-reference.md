# API リファレンス

## Python パッケージ: android-screen-stream

### StreamConfig

ストリーミング設定を管理するデータクラス。

```python
from android_screen_stream import StreamConfig

# デフォルト設定
config = StreamConfig()

# カスタム設定
config = StreamConfig(
    max_size=1080,      # 短辺の最大ピクセル数
    max_fps=60,         # 最大フレームレート
    bit_rate=8_000_000, # ビットレート (bps)
    video_codec="h264", # コーデック
)

# プリセット
config = StreamConfig.low_bandwidth()  # 720p, 15fps, 1Mbps
config = StreamConfig.balanced()       # 1080p, 30fps, 4Mbps
config = StreamConfig.high_quality()   # 1080p, 60fps, 8Mbps
```

#### 属性

| 属性 | 型 | デフォルト | 説明 |
|------|-----|---------|------|
| `max_size` | `int` | `720` | 短辺の最大ピクセル数 |
| `max_fps` | `int` | `30` | 最大フレームレート |
| `bit_rate` | `int` | `2_000_000` | ビットレート (bps) |
| `video_codec` | `str` | `"h264"` | ビデオコーデック ("h264", "h265", "av1") |
| `i_frame_interval` | `int` | `1` | I-frame 間隔（秒）。小さいほど途中参加の復帰が速い |
| `prepend_header_to_sync_frames` | `bool` | `true` | 同期フレーム(IDR等)にSPS/PPS等のヘッダを付けるようエンコーダに要求（端末依存） |

#### クラスメソッド

- `low_bandwidth()` - 低帯域向けプリセット (720p, 15fps, 1Mbps)
- `balanced()` - バランスプリセット (1080p, 30fps, 4Mbps)
- `high_quality()` - 高品質プリセット (1080p, 60fps, 8Mbps)

---

### ScrcpyClient

低レベルの scrcpy-server クライアント。直接 H.264 ストリームを取得します。

```python
from android_screen_stream import ScrcpyClient, StreamConfig

# コンテキストマネージャ使用（推奨）
async with ScrcpyClient(
    serial="emulator-5554",
    server_jar="vendor/scrcpy-server.jar",
    config=StreamConfig.balanced(),
) as client:
    async for chunk in client.stream():
        process(chunk)

# 手動管理
client = ScrcpyClient("emulator-5554", server_jar="vendor/scrcpy-server.jar")
await client.start()
try:
    async for chunk in client.stream():
        process(chunk)
finally:
    await client.stop()
```

#### コンストラクタ

```python
ScrcpyClient(
    serial: str,           # デバイスシリアル番号
    server_jar: str,       # scrcpy-server.jar のパス
    config: StreamConfig,  # ストリーミング設定（省略可）
    local_port: int = 0,   # ローカルポート（0=自動）
)
```

#### メソッド

| メソッド | 説明 |
|----------|------|
| `await start()` | サーバーを起動して接続 |
| `await stop()` | サーバーを停止 |
| `stream() -> AsyncIterator[bytes]` | H.264 チャンクを順次取得 |

#### プロパティ

| プロパティ | 型 | 説明 |
|-----------|-----|------|
| `is_running` | `bool` | クライアントが動作中かどうか |

---

### StreamSession

マルチキャスト対応のストリーミングセッション。複数クライアントへの同時配信をサポートします。

途中参加（late join）で白画面にならないよう、サーバ側で直近の SPS/PPS と最新GOP(IDR〜現在) を保持し、
join 時に "初期化できる塊" を先頭に送る実装になっています。

詳細: [docs/late-join.md](late-join.md)

```python
from android_screen_stream import StreamSession, StreamConfig

session = StreamSession(
    serial="emulator-5554",
    server_jar="vendor/scrcpy-server.jar",
    config=StreamConfig.balanced(),
)
await session.start()

# 購読（複数クライアント対応）
async for chunk in session.subscribe():
    await websocket.send_bytes(chunk)

# 設定変更（セッション再起動）
await session.update_config(StreamConfig.high_quality())

await session.stop()
```

#### コンストラクタ

```python
StreamSession(
    serial: str,           # デバイスシリアル番号
    server_jar: str,       # scrcpy-server.jar のパス
    config: StreamConfig,  # ストリーミング設定（省略可）
)
```

#### メソッド

| メソッド | 説明 |
|----------|------|
| `await start()` | セッションを開始 |
| `await stop()` | セッションを停止 |
| `subscribe() -> AsyncIterator[bytes]` | ストリームを購読 |
| `await update_config(config)` | 設定を更新して再起動 |

#### プロパティ

| プロパティ | 型 | 説明 |
|-----------|-----|------|
| `is_running` | `bool` | セッションが動作中かどうか |
| `stats` | `StreamStats` | 統計情報 |

---

### StreamManager

複数デバイスのセッション管理。

```python
from android_screen_stream import StreamManager, StreamConfig

manager = StreamManager(
    server_jar="vendor/scrcpy-server.jar",
    default_config=StreamConfig.balanced(),
)

# セッションを取得または作成
session = await manager.get_or_create("emulator-5554")

# 全セッションを停止
await manager.stop_all()
```

#### コンストラクタ

```python
StreamManager(
    server_jar: str,              # scrcpy-server.jar のパス
    default_config: StreamConfig, # デフォルトの設定（省略可）
)
```

#### メソッド

| メソッド | 説明 |
|----------|------|
| `await get_or_create(serial, config=None)` | セッションを取得または作成 |
| `await stop(serial)` | 指定デバイスのセッションを停止 |
| `await stop_all()` | 全セッションを停止 |

#### プロパティ

| プロパティ | 型 | 説明 |
|-----------|-----|------|
| `active_sessions` | `list[str]` | アクティブなセッションのシリアル一覧 |

---

## NPM パッケージ: react-android-screen

### H264Player

H.264 ストリーミングプレイヤーコンポーネント。

```tsx
import { H264Player } from 'react-android-screen'

<H264Player
  wsUrl="/api/ws/stream/emulator-5554"
  className="w-full max-w-2xl"
  onConnected={() => console.log('connected')}
  onDisconnected={() => console.log('disconnected')}
  onError={(error) => console.error(error)}
  fps={30}
  autoReconnect={true}
  reconnectInterval={3000}
/>
```

#### Props

| Prop | 型 | デフォルト | 説明 |
|------|-----|---------|------|
| `wsUrl` | `string` | 必須 | WebSocket URL |
| `className` | `string` | `""` | CSS クラス |
| `onConnected` | `() => void` | - | 接続時コールバック |
| `onDisconnected` | `() => void` | - | 切断時コールバック |
| `onError` | `(error: string) => void` | - | エラー時コールバック |
| `fps` | `number` | `30` | 想定フレームレート |
| `autoReconnect` | `boolean` | `true` | 自動再接続 |
| `reconnectInterval` | `number` | `3000` | 再接続間隔 (ms) |

---

### useAndroidStream

低レベルのカスタムフック。カスタム UI を構築する場合に使用します。

```tsx
import { useAndroidStream } from 'react-android-screen'

function CustomPlayer() {
  const { videoRef, status, stats, connect, disconnect } = useAndroidStream({
    wsUrl: '/api/ws/stream/emulator-5554',
    autoConnect: true,
    fps: 30,
    onConnected: () => console.log('connected'),
    onDisconnected: () => console.log('disconnected'),
    onError: (error) => console.error(error),
  })

  return (
    <div>
      <video ref={videoRef} autoPlay muted />
      <p>Status: {status}</p>
      <p>Received: {stats.bytes} bytes, {stats.chunks} chunks</p>
      <button onClick={connect}>Connect</button>
      <button onClick={disconnect}>Disconnect</button>
    </div>
  )
}
```

#### Options

| Option | 型 | デフォルト | 説明 |
|--------|-----|---------|------|
| `wsUrl` | `string` | 必須 | WebSocket URL |
| `autoConnect` | `boolean` | `true` | 自動接続 |
| `fps` | `number` | `30` | 想定フレームレート |
| `onConnected` | `() => void` | - | 接続時コールバック |
| `onDisconnected` | `() => void` | - | 切断時コールバック |
| `onError` | `(error: string) => void` | - | エラー時コールバック |

#### 戻り値

| プロパティ | 型 | 説明 |
|-----------|-----|------|
| `videoRef` | `RefObject<HTMLVideoElement>` | video 要素への参照 |
| `status` | `StreamStatus` | 接続状態 |
| `stats` | `StreamStats` | 統計情報 |
| `connect` | `() => void` | 接続関数 |
| `disconnect` | `() => void` | 切断関数 |

#### StreamStatus

```typescript
type StreamStatus = 'disconnected' | 'connecting' | 'connected' | 'error'
```

#### StreamStats

```typescript
interface StreamStats {
  bytes: number   // 受信バイト数
  chunks: number  // 受信チャンク数
}
```
