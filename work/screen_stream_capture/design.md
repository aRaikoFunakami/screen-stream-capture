# 設計書: Screen Stream Capture System

## 概要

複数の Android デバイスの画面を同時に Web ブラウザへ動画配信し、任意の瞬間にサーバー側で JPEG キャプチャを生成、クライアントが Downloads/ に保存できる Web システム。

### 設計の根本思想

> **「スクリーンショット取得ツール」ではなく「画面ストリーム購読・オンデマンド切り出しシステム」**

常にストリームを受信し続け、必要な瞬間に最新フレームを切り出す。Pull 型ではなく **Push/Stream 型**の設計を徹底する。

---

## 1. システム全体構成

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Server (Python)                                │
│  ┌─────────────────────────────────────────────────────────────────────────┐
│  │                           FastAPI (async)                               │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │  │DeviceMonitor│  │ScrcpyStream │  │  Fmp4Muxer  │  │  Capture    │    │
│  │  │             │  │  Manager    │  │  (ffmpeg)   │  │  Service    │    │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘    │
│  │         │                │                │                │            │
│  │         ▼                ▼                ▼                ▼            │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  │                      DeviceRegistry                             │   │
│  │  │              (デバイス情報・ストリーム状態管理)                  │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │
│  │                                                                         │
│  │  ┌─────────────┐  ┌─────────────────────┐  ┌─────────────┐            │
│  │  │ Appium      │  │  API Layer          │  │  WS Layer   │            │
│  │  │ Manager     │  │  (REST endpoints)   │  │  (streams)  │            │
│  │  └─────────────┘  └─────────────────────┘  └─────────────┘            │
│  └─────────────────────────────────────────────────────────────────────────┘
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
          ▼                        ▼                        ▼
   ┌─────────────┐          ┌─────────────┐          ┌─────────────┐
   │  Android    │          │  Android    │          │  Android    │
   │  Device 1   │          │  Device 2   │          │  Device N   │
   │  (scrcpy)   │          │  (scrcpy)   │          │  (scrcpy)   │
   └─────────────┘          └─────────────┘          └─────────────┘
```

---

## 2. 技術スタック

### バックエンド

| 役割 | 技術 | 理由 |
|------|------|------|
| Web Framework | **FastAPI** | 非同期処理に特化、WebSocket 対応 |
| 非同期処理 | **asyncio** | Python 標準、ノンブロッキング I/O |
| パッケージ管理 | **uv** | 高速・再現性の高い依存関係管理 |
| 画面取得 | **scrcpy** | 高品質な H.264 ストリーム出力 |
| 動画変換 | **ffmpeg** | H.264 → fMP4 変換の業界標準 |
| デバイス検知 | **adb track-devices** | イベント駆動でポーリング不要 |
| キャプチャ生成 | **OpenCV / Pillow** | フレームから JPEG 生成 |

### フロントエンド

| 役割 | 技術 | 理由 |
|------|------|------|
| UI Framework | **React** | コンポーネントベースの UI 構築 |
| ビルドツール | **Vite** | 高速な開発サーバー・ビルド |
| スタイリング | **TailwindCSS** | ユーティリティファースト CSS |
| 動画再生 | **MSE (Media Source Extensions)** | ブラウザ標準の動画ストリーミング API |

---

## 3. 映像配信アーキテクチャ

### 採用方式: MSE + fMP4/H264

```
┌──────────┐     H.264      ┌──────────┐     fMP4      ┌──────────┐
│  scrcpy  │ ──────────────>│  ffmpeg  │ ─────────────>│ FastAPI  │
│ (device) │   raw stream   │ (muxer)  │  fragments   │ (server) │
└──────────┘                └──────────┘               └────┬─────┘
                                                            │
                                            HTTP Streaming  │
                                            (StreamingResponse)
                                                            │
                                                            ▼
                                                     ┌──────────┐
                                                     │ Browser  │
                                                     │  (MSE)   │
                                                     │ <video>  │
                                                     └──────────┘
```

### データフローの詳細

1. **scrcpy → ffmpeg**
   - scrcpy が Android から H.264 ストリームを取得
   - TCP ソケット経由で ffmpeg に転送

2. **ffmpeg による fMP4 変換**
   ```bash
   ffmpeg -i pipe:0 -c:v copy -f mp4 \
     -movflags frag_keyframe+empty_moov+default_base_moof \
     -tune zerolatency \
     pipe:1
   ```
   - `frag_keyframe`: キーフレームごとに断片化
   - `empty_moov`: MSE 用の即時ヘッダー生成
   - `-tune zerolatency`: 遅延最小化

3. **FastAPI → ブラウザ**
   - `StreamingResponse` で fMP4 フラグメントを配信
   - 初期セグメント（Init Segment）をキャッシュし、新規接続時に送信

4. **ブラウザ側 MSE 処理**
   ```javascript
   const mediaSource = new MediaSource();
   video.src = URL.createObjectURL(mediaSource);
   
   mediaSource.addEventListener('sourceopen', () => {
     const sourceBuffer = mediaSource.addSourceBuffer('video/mp4; codecs="avc1.64001f"');
     // ストリームからのチャンクを appendBuffer で追加
   });
   ```

### 設計上の重要ポイント

| ポイント | 設計 |
|----------|------|
| **Init Segment キャッシュ** | ffmpeg 初期出力（ftyp/moov）を保持し、途中参加者にも送信 |
| **プロセス共有** | デバイス 1 台につき ffmpeg プロセス 1 つ、複数クライアントで共有 |
| **配信ハブ** | `asyncio.Queue` でマルチキャスト配信 |
| **切断処理** | 全クライアント切断時に ffmpeg プロセス終了 |

---

## 4. モジュール設計

### 4.1 DeviceMonitor

**責務**: ADB デバイスの接続・切断イベントを監視

```python
class DeviceMonitor:
    """adb track-devices を購読し、デバイス変更イベントを発行"""
    
    async def start(self) -> None:
        """監視開始（非同期ループ）"""
    
    async def stop(self) -> None:
        """監視停止"""
    
    def on_device_connected(self, callback: Callable[[str], None]) -> None:
        """接続時コールバック登録"""
    
    def on_device_disconnected(self, callback: Callable[[str], None]) -> None:
        """切断時コールバック登録"""
```

**実装方針**:
- `adb track-devices` をサブプロセスで実行
- stdout をイベントループで監視
- **ポーリング禁止**: `adb devices` の定期実行は行わない

### 4.2 DeviceRegistry

**責務**: デバイス情報とストリーム状態の一元管理

```python
class DeviceRegistry:
    """デバイス情報のキャッシュと状態管理"""
    
    async def register(self, serial: str, info: DeviceInfo) -> None:
        """デバイス登録"""
    
    async def unregister(self, serial: str) -> None:
        """デバイス削除"""
    
    def get(self, serial: str) -> Optional[DeviceInfo]:
        """デバイス情報取得"""
    
    def list_all(self) -> List[DeviceInfo]:
        """全デバイス一覧"""
    
    async def set_stream_status(self, serial: str, status: StreamStatus) -> None:
        """ストリーム状態更新"""
```

### 4.3 ScrcpyStreamManager

**責務**: scrcpy プロセスのライフサイクル管理

```python
class ScrcpyStreamManager:
    """デバイスごとの scrcpy プロセス管理"""
    
    async def start_stream(
        self,
        serial: str,
        max_fps: int = 15,
        max_resolution: int = 720,
        bitrate: str = "2M"
    ) -> AsyncIterator[bytes]:
        """ストリーム開始、H.264 データを yield"""
    
    async def stop_stream(self, serial: str) -> None:
        """ストリーム停止"""
    
    async def get_latest_frame(self, serial: str) -> Optional[np.ndarray]:
        """キャプチャ用の最新フレーム取得"""
```

**パラメータ化必須項目**:
- `max_fps`: 最大フレームレート（デフォルト: 15）
- `max_resolution`: 最大解像度（デフォルト: 720）
- `bitrate`: ビットレート（デフォルト: 2M）

### 4.4 Fmp4Muxer

**責務**: ffmpeg を使用した H.264 → fMP4 変換

```python
class Fmp4Muxer:
    """ffmpeg による fMP4 変換"""
    
    async def start(self, h264_stream: AsyncIterator[bytes]) -> None:
        """変換開始"""
    
    async def subscribe(self) -> AsyncIterator[bytes]:
        """fMP4 フラグメントを購読"""
    
    def get_init_segment(self) -> bytes:
        """初期セグメント（ftyp/moov）を取得"""
    
    async def stop(self) -> None:
        """変換停止"""
```

### 4.5 CaptureService

**責務**: 最新フレームからの JPEG 生成

```python
class CaptureService:
    """キャプチャ生成サービス"""
    
    async def capture(
        self,
        serial: str,
        quality: int = 85
    ) -> bytes:
        """JPEG バイナリを生成"""
    
    def generate_filename(self, serial: str) -> str:
        """ファイル名生成: {serial}_{YYYYMMDD_HHMMSS_mmm}.jpg"""
```

### 4.6 AppiumManager

**責務**: Appium サーバーのライフサイクル管理

```python
class AppiumManager:
    """Appium サーバー管理"""
    
    async def start(self) -> int:
        """起動し、割り当てポートを返す"""
    
    async def stop(self) -> None:
        """停止（terminate → timeout → kill）"""
    
    async def wait_ready(self, timeout: float = 30.0) -> bool:
        """起動完了を待機"""
    
    @property
    def port(self) -> Optional[int]:
        """現在のポート"""
```

**実装方針**:
- FastAPI の lifespan 内で管理
- 空きポート確保後に起動
- readiness チェック実施
- SIGINT/SIGTERM/例外時も確実に停止

### 4.7 StreamSession（配信ハブ）

**責務**: クライアント単位の配信制御

```python
class StreamSession:
    """クライアントへのストリーム配信管理"""
    
    async def subscribe(self, serial: str) -> asyncio.Queue[bytes]:
        """購読開始、専用キューを返す"""
    
    async def unsubscribe(self, serial: str, queue: asyncio.Queue) -> None:
        """購読終了"""
    
    async def broadcast(self, serial: str, data: bytes) -> None:
        """全購読者にデータ配信"""
```

---

## 5. API 設計

### REST API

#### `GET /api/devices`

デバイス一覧を取得

**Response**:
```json
[
  {
    "serial": "emulator-5554",
    "state": "device",
    "model": "Pixel 4",
    "manufacturer": "Google",
    "isEmulator": true,
    "lastSeen": "2026-01-25T10:30:00Z"
  }
]
```

#### `POST /api/devices/{serial}/capture`

指定デバイスの画面をキャプチャ

**Query Parameters**:
- `quality`: JPEG 品質（1-100, デフォルト: 85）

**Response**: `image/jpeg`

**Headers**:
```
Content-Disposition: attachment; filename="emulator-5554_20260125_103000_123.jpg"
```

#### `GET /healthz`

ヘルスチェック

**Response**:
```json
{
  "status": "ok",
  "appium": "running",
  "devices": 2
}
```

### Streaming API

#### `GET /api/stream/{serial}`

fMP4 ストリームを配信（HTTP Streaming）

**Response**: `video/mp4`（StreamingResponse）

**処理フロー**:
1. Init Segment を送信
2. 以降、fMP4 フラグメントを継続的に送信

### WebSocket API

#### `WS /ws/devices`

デバイス状態変更をリアルタイム通知

**Events**:
```json
{"type": "added", "device": {...}}
{"type": "removed", "serial": "..."}
{"type": "stateChanged", "serial": "...", "state": "device"}
```

---

## 6. フロントエンド設計

### コンポーネント構成

```
App
├── Header
│   └── HealthStatus
├── PanelGrid
│   ├── Panel (×N)
│   │   ├── DeviceSelector
│   │   ├── VideoPlayer (MSE)
│   │   ├── CaptureButton
│   │   └── StatusIndicator
│   └── AddPanelButton
└── Footer
```

### 主要コンポーネント

#### Panel

```typescript
interface PanelProps {
  id: string;
  onRemove: () => void;
}

const Panel: React.FC<PanelProps> = ({ id, onRemove }) => {
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null);
  // ...
};
```

#### VideoPlayer (MSE)

```typescript
interface VideoPlayerProps {
  serial: string;
}

const VideoPlayer: React.FC<VideoPlayerProps> = ({ serial }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  
  useEffect(() => {
    const mediaSource = new MediaSource();
    // MSE セットアップ
  }, [serial]);
  
  return <video ref={videoRef} autoPlay muted />;
};
```

### 状態管理

- **デバイス一覧**: WebSocket 経由でリアルタイム更新
- **パネル管理**: React useState でローカル管理
- **ストリーム状態**: 各 Panel で独立管理

---

## 7. エラーハンドリング

### サーバー側

| シナリオ | 対応 |
|----------|------|
| デバイス切断 | scrcpy 停止、ストリーム解放、クライアント通知 |
| ffmpeg クラッシュ | プロセス再起動、クライアントに再接続促進 |
| Appium 異常終了 | 自動再起動、readiness チェック後に復帰 |

### クライアント側

| シナリオ | 対応 |
|----------|------|
| ストリーム切断 | 自動再接続（exponential backoff） |
| MSE エラー | SourceBuffer リセット、ストリーム再取得 |
| キャプチャ失敗 | エラートースト表示、リトライボタン |

---

## 8. パフォーマンス考慮事項

### メモリ管理

- **フレームバッファ**: 最新フレームのみ保持（リングバッファ不使用）
- **ストリームバッファ**: 適切なチャンクサイズ（64KB 推奨）
- **クライアントキュー**: 上限設定（遅いクライアントは切断）

### CPU 負荷

- **ffmpeg**: `-c:v copy` でトランスコード不要
- **FastAPI**: バイナリ転送のみで処理負荷最小

### 同時接続

- **デバイス数**: 実質的に adb の制限に依存
- **クライアント数**: asyncio.Queue によるマルチキャスト

---

## 9. セキュリティ

本システムはセキュリティを**一切考慮しない**設計とする。

- 認証・認可: なし
- HTTPS: 不要
- CORS: 全許可
- 入力検証: 最小限（型チェックのみ）

---

## 10. 受け入れ条件（DoD）

- [ ] デバイス接続/切断が即座に UI に反映される
- [ ] 複数デバイスの画面を同時に動画再生できる
- [ ] Capture で JPEG が即ダウンロードされる
- [ ] サーバー終了時に scrcpy / ffmpeg / Appium が残らない
- [ ] 高頻度ポーリングが存在しない（ログで確認可能）
- [ ] 途中参加のクライアントも正常に再生開始できる

---

## 11. 非機能要件

| 項目 | 要件 |
|------|------|
| 遅延 | 1 秒以内（ネットワーク遅延除く） |
| 同時デバイス | 5 台以上 |
| 同時クライアント | 10 接続以上（デバイスあたり） |
| 起動時間 | 5 秒以内（Appium 除く） |
| メモリ使用量 | 500MB 以下（10 ストリーム時） |
