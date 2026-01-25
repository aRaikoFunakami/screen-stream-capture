# 調査メモ: Screen Stream Capture System

## 概要

本ドキュメントは、実装に先立って行った技術調査の結果をまとめたものである。

---

## 1. 映像配信方式の比較検討

### 検討した方式

| 方式 | 概要 | 評価 |
|------|------|------|
| **MSE + fMP4** | ブラウザ標準 API でストリーミング | ✅ **採用** |
| WebRTC | P2P リアルタイム通信 | ❌ 複雑すぎる |
| MJPEG | JPEG 連続送信 | ❌ 効率が悪い |
| HLS/DASH | セグメント分割配信 | ❌ 遅延が大きい |

### MSE + fMP4 採用理由

1. **ブラウザ標準**: 追加ライブラリ不要
2. **単方向配信**: サーバー主導でシンプル
3. **scrcpy 親和性**: H.264 出力をそのまま利用
4. **NAT/ICE 不要**: WebRTC のような複雑な設定不要
5. **スケーラビリティ**: MVP から本番まで構造変更なし

---

## 2. ffmpeg による fMP4 変換

### 重要な movflags

```bash
ffmpeg -i pipe:0 -c:v copy -f mp4 \
  -movflags frag_keyframe+empty_moov+default_base_moof \
  pipe:1
```

| フラグ | 役割 |
|--------|------|
| `frag_keyframe` | キーフレームごとに断片化 |
| `empty_moov` | 即時ヘッダー生成（MSE 必須） |
| `default_base_moof` | MSE 互換性向上 |

### `-tune zerolatency`

- 遅延を最小化するエンコード設定
- ただし `-c:v copy` 時は不要（トランスコードしないため）

### パイプ処理の注意点

- `pipe:0`: 標準入力
- `pipe:1`: 標準出力
- バッファリングに注意（データが溜まってから出力される可能性）

---

## 3. scrcpy の利用方法

### 起動オプション

```bash
scrcpy --serial <serial> \
  --video-codec=h264 \
  --no-audio \
  --no-control \
  --max-fps=15 \
  --max-size=720 \
  --video-bit-rate=2M \
  --video-source=display \
  --no-window
```

| オプション | 説明 |
|------------|------|
| `--video-codec=h264` | H.264 コーデック指定 |
| `--no-audio` | 音声なし |
| `--no-control` | 操作無効化 |
| `--max-fps=15` | 最大 FPS |
| `--max-size=720` | 最大解像度 |
| `--video-bit-rate=2M` | ビットレート |
| `--no-window` | GUI なし |

### ストリーム取得方法

**方法 1: TCP ソケット**
```bash
scrcpy --tcpip=<ip>:<port> --video-codec=h264 ...
```

**方法 2: stdout 出力**
```bash
scrcpy --video-codec=h264 --record=- --record-format=h264 ...
```

→ 検証が必要。`--record=-` で stdout に出力できるか確認。

### scrcpy-server.jar

- scrcpy は内部で `scrcpy-server.jar` を Android にプッシュ
- サーバーが H.264 ストリームを生成
- ADB forward で PC に転送

---

## 4. adb track-devices

### 基本動作

```bash
adb track-devices
```

- 接続を維持し、デバイス変更時にイベント送信
- `adb devices` のポーリング不要

### 出力形式

```
<4桁16進数長さ><デバイスリスト>
```

例:
```
001Aemulator-5554	device
```

### Python での実装

```python
import asyncio

async def track_devices():
    proc = await asyncio.create_subprocess_exec(
        'adb', 'track-devices',
        stdout=asyncio.subprocess.PIPE
    )
    
    while True:
        # 4バイトの長さを読み取り
        length_hex = await proc.stdout.read(4)
        length = int(length_hex, 16)
        
        # デバイスリストを読み取り
        data = await proc.stdout.read(length)
        devices = parse_device_list(data.decode())
        
        yield devices
```

---

## 5. MSE (Media Source Extensions)

### 基本的な使い方

```javascript
const video = document.querySelector('video');
const mediaSource = new MediaSource();
video.src = URL.createObjectURL(mediaSource);

mediaSource.addEventListener('sourceopen', () => {
  const sourceBuffer = mediaSource.addSourceBuffer(
    'video/mp4; codecs="avc1.64001f"'
  );
  
  // ストリームからデータを受け取り
  fetch('/api/stream/device1')
    .then(response => response.body.getReader())
    .then(reader => {
      function push() {
        reader.read().then(({ done, value }) => {
          if (done) return;
          sourceBuffer.appendBuffer(value);
          push();
        });
      }
      push();
    });
});
```

### Init Segment の重要性

- MSE は最初に `ftyp` と `moov` ボックスが必要
- これがないと途中参加者は再生開始できない
- サーバー側でキャッシュし、新規接続時に先行送信

### コーデック文字列

| 解像度 | コーデック文字列 |
|--------|------------------|
| 720p | `avc1.64001f` |
| 1080p | `avc1.640028` |
| 4K | `avc1.640033` |

→ 実際の scrcpy 出力に合わせて調整が必要

---

## 6. HTTP Streaming vs WebSocket

### 比較

| 項目 | HTTP Streaming | WebSocket |
|------|----------------|-----------|
| セットアップ | シンプル | ハンドシェイク必要 |
| 双方向通信 | 不可 | 可能 |
| ブラウザ互換性 | 良好 | 良好 |
| 負荷 | 低 | やや高 |
| 再接続 | 自動（fetch） | 手動実装 |

### 結論

- **映像配信**: HTTP Streaming（StreamingResponse）
- **デバイス通知**: WebSocket

理由: 映像は一方向配信のみなので、シンプルな HTTP Streaming が最適。

---

## 7. Python 非同期サブプロセス

### asyncio.create_subprocess_exec

```python
import asyncio

async def run_ffmpeg():
    proc = await asyncio.create_subprocess_exec(
        'ffmpeg', '-i', 'pipe:0', '-f', 'mp4',
        '-movflags', 'frag_keyframe+empty_moov',
        'pipe:1',
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL
    )
    
    # stdin に書き込み
    proc.stdin.write(h264_data)
    await proc.stdin.drain()
    
    # stdout から読み取り
    chunk = await proc.stdout.read(65536)
```

### 注意点

1. **stderr の処理**: DEVNULL に捨てるか、別途ログ出力
2. **プロセス終了**: `proc.terminate()` → `proc.wait()` → `proc.kill()`
3. **パイプバッファ**: 大きなデータはデッドロックの可能性

---

## 8. フレームデコード

### H.264 → numpy array

**OpenCV 使用**:
```python
import cv2
import numpy as np

# H.264 データを一時ファイル or VideoCapture で処理
# → リアルタイムストリームでは複雑

# ffmpeg でデコードするほうが確実
```

**ffmpeg + rawvideo 出力**:
```bash
ffmpeg -i pipe:0 -f rawvideo -pix_fmt rgb24 pipe:1
```

→ JPEG 生成のためにデコードが必要。検討が必要。

### 代替案: scrcpy の screenshot 機能

```bash
scrcpy --serial <serial> --screenshot <path>
```

→ ストリームとは別にスナップショット取得も可能か？

---

## 9. Appium 管理

### 起動コマンド

```bash
appium --port <port> --base-path /wd/hub
```

### Readiness チェック

```bash
curl http://localhost:<port>/status
```

→ 200 OK で起動完了

### 空きポート確保

```python
import socket

def find_free_port():
    with socket.socket() as s:
        s.bind(('', 0))
        return s.getsockname()[1]
```

### 停止手順

1. `SIGTERM` 送信
2. 5 秒待機
3. 応答なければ `SIGKILL`
4. プロセス完了待機

---

## 10. 未解決課題

### 高優先度

1. **scrcpy stdout 出力**: `--record=-` で H.264 を stdout に出力できるか検証
2. **ffmpeg パイプ遅延**: バッファリングによる遅延の程度を計測
3. **Init Segment 検出**: fMP4 の ftyp/moov ボックスをどう検出するか

### 中優先度

1. **フレームデコード方式**: キャプチャ用のデコードをどこで行うか
2. **複数クライアント負荷**: 10 接続時のメモリ・CPU 使用量
3. **再接続ロジック**: クライアント側の再接続実装

### 低優先度

1. **コーデック文字列**: scrcpy 出力に合わせた正確な値
2. **解像度変更**: 動的な解像度変更対応
3. **ログ出力**: 適切なログレベル設計

---

## 11. 参考リンク

### 公式ドキュメント

- [scrcpy GitHub](https://github.com/Genymobile/scrcpy)
- [ffmpeg Documentation](https://ffmpeg.org/documentation.html)
- [MSE Specification](https://www.w3.org/TR/media-source/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

### 参考記事

- [MSE でのライブストリーミング](https://developer.mozilla.org/en-US/docs/Web/API/Media_Source_Extensions_API)
- [ffmpeg fMP4 出力](https://ffmpeg.org/ffmpeg-formats.html#mov_002c-mp4_002c-ismv)

---

## 12. 検証ログ

### 2026-01-25: 初期調査

- order.md, investigations.md を精読
- MSE + fMP4 方式を採用決定
- 設計書・計画書を作成
