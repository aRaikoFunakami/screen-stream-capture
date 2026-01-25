# android-screen-stream

Android デバイスの画面をリアルタイムでストリーミングする Python ライブラリ

## 特徴

- 🚀 低遅延 H.264 ストリーミング
- 📱 複数デバイス同時対応
- 🔧 解像度・FPS・ビットレート設定可能
- 🔌 マルチキャスト対応（複数クライアントへの同時配信）

## 前提条件

- Python 3.11+
- adb (Android Debug Bridge)
- scrcpy-server.jar

## インストール

```bash
# editable install
uv add --editable /path/to/packages/android-screen-stream
```

## 使い方

### 低レベルクライアント

```python
from android_screen_stream import ScrcpyClient, StreamConfig

config = StreamConfig(max_size=1080, max_fps=60, bit_rate=8_000_000)

async with ScrcpyClient("emulator-5554", server_jar="path/to/scrcpy-server.jar", config=config) as client:
    async for chunk in client.stream():
        # raw H.264 データを処理
        process(chunk)
```

### セッション管理（マルチキャスト）

```python
from android_screen_stream import StreamSession, StreamConfig

session = StreamSession(
    "emulator-5554",
    server_jar="path/to/scrcpy-server.jar",
    config=StreamConfig.balanced(),
)
await session.start()

# 購読（複数クライアントが同時に購読可能）
async for chunk in session.subscribe():
    await websocket.send_bytes(chunk)

# 設定の動的変更
await session.update_config(StreamConfig.high_quality())

# 停止
await session.stop()
```

### StreamManager（全デバイス管理）

```python
from android_screen_stream import StreamManager, StreamConfig

manager = StreamManager(
    server_jar="path/to/scrcpy-server.jar",
    default_config=StreamConfig.balanced(),
)

# セッション取得または作成
session = await manager.get_or_create("emulator-5554")

# 購読
async for chunk in session.subscribe():
    await websocket.send_bytes(chunk)

# 全停止
await manager.stop_all()
```

## StreamConfig プリセット

| プリセット | 解像度 | FPS | ビットレート |
|-----------|--------|-----|-------------|
| `StreamConfig()` | 720p | 30 | 2Mbps |
| `StreamConfig.low_bandwidth()` | 720p | 15 | 1Mbps |
| `StreamConfig.balanced()` | 1080p | 30 | 4Mbps |
| `StreamConfig.high_quality()` | 1080p | 60 | 8Mbps |

## API リファレンス

### StreamConfig

```python
@dataclass
class StreamConfig:
    max_size: int = 720          # 短辺の最大ピクセル数
    max_fps: int = 30            # 最大フレームレート
    bit_rate: int = 2_000_000    # ビットレート (bps)
    video_codec: str = "h264"    # "h264", "h265", "av1"
```

### ScrcpyClient

```python
class ScrcpyClient:
    def __init__(self, serial: str, server_jar: str, config: StreamConfig = None): ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def stream(self) -> AsyncIterator[bytes]: ...
    
    # コンテキストマネージャ対応
    async def __aenter__(self) -> ScrcpyClient: ...
    async def __aexit__(self, ...): ...
```

### StreamSession

```python
class StreamSession:
    def __init__(self, serial: str, server_jar: str, config: StreamConfig = None): ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def subscribe(self) -> AsyncIterator[bytes]: ...
    async def update_config(self, config: StreamConfig) -> None: ...
    
    @property
    def is_running(self) -> bool: ...
    @property
    def subscriber_count(self) -> int: ...
```

## ライセンス

MIT
