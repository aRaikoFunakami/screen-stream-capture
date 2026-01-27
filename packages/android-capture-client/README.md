# android-capture-client

Android スクリーンキャプチャクライアントライブラリ

screen-stream-capture バックエンドの WebSocket キャプチャ API に接続し、
任意のタイミングでスクリーンショットを取得するための Python ライブラリです。

## 特徴

- 🔌 **常時接続**: WebSocket でバックエンドと常時接続し、いつでもキャプチャ可能
- 🧵 **非同期設計**: バックグラウンドスレッドで動作し、メインアプリをブロックしない
- 🛡️ **安全なリソース管理**: コンテキストマネージャで確実に接続を解放
- 📸 **シンプル API**: `capture()` メソッドで即座にスクリーンショットを取得

## インストール

```bash
uv add --editable /path/to/packages/android-capture-client
```

## クイックスタート

### 基本的な使い方

```python
import asyncio
from android_capture_client import CaptureClient

async def main():
    async with CaptureClient("emulator-5554", backend_url="ws://localhost:8000") as client:
        # スクリーンショットを取得
        result = await client.capture()
        
        # JPEG データを保存
        with open("screenshot.jpg", "wb") as f:
            f.write(result.jpeg_data)
        
        print(f"Captured: {result.width}x{result.height}")

asyncio.run(main())
```

### 同期コードからの利用（バックグラウンドスレッド）

```python
from android_capture_client import CaptureSession

# セッション開始（バックグラウンドスレッドで動作）
session = CaptureSession("emulator-5554", backend_url="ws://localhost:8000")
session.start()

# メインスレッドをブロックせずにキャプチャ
result = session.capture(timeout=5.0)
print(f"Captured: {result.width}x{result.height}")

# 複数回キャプチャ可能
for i in range(3):
    result = session.capture()
    with open(f"screenshot_{i}.jpg", "wb") as f:
        f.write(result.jpeg_data)

# 終了時に明示的に停止
session.stop()
```

### コンテキストマネージャでの利用

```python
from android_capture_client import CaptureSession

with CaptureSession("emulator-5554") as session:
    result = session.capture()
    # ...
# 自動的に接続が解放される
```

## API リファレンス

### CaptureClient（非同期）

```python
class CaptureClient:
    def __init__(
        self,
        serial: str,
        backend_url: str = "ws://localhost:8000",
    ): ...
    
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def capture(
        self,
        quality: int = 80,
        save: bool = False,
    ) -> CaptureResult: ...
```

### CaptureSession（同期ラッパー）

```python
class CaptureSession:
    def __init__(
        self,
        serial: str,
        backend_url: str = "ws://localhost:8000",
    ): ...
    
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def capture(
        self,
        quality: int = 80,
        save: bool = False,
        timeout: float = 10.0,
    ) -> CaptureResult: ...
```

### CaptureResult

```python
@dataclass
class CaptureResult:
    capture_id: str
    serial: str
    width: int
    height: int
    jpeg_data: bytes
    captured_at: str
    path: str | None  # save=True の場合のみ
```

## デモアプリ

インタラクティブな CUI デモが含まれています:

```bash
# バックエンドが起動している状態で実行
capture-demo --serial emulator-5554 --backend ws://localhost:8000
```

## 注意事項

- バックエンドが起動していること
- 指定したデバイスが adb で接続されていること
- 最初のキャプチャは約 0.5〜1 秒かかる場合があります（デコーダ起動待ち）
- 2 回目以降は約 60〜120ms で完了します

## ライセンス

MIT
