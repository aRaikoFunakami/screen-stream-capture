# 方法D: scrcpy-serverへの直接接続計画

## 調査結果サマリー

### 重要な発見

scrcpy-serverには**スタンドアロンモード**用のオプションが既に存在する！

```bash
adb shell CLASSPATH=/data/local/tmp/scrcpy-server.jar \
    app_process / com.genymobile.scrcpy.Server 3.3.4 \
    tunnel_forward=true audio=false control=false cleanup=false \
    raw_stream=true max_size=1920
```

`raw_stream=true` を指定すると以下が無効化される:
- `send_device_meta=false` - デバイス名の送信を無効化
- `send_frame_meta=false` - 12バイトのパケットヘッダーを無効化
- `send_dummy_byte=false` - forward接続時のダミーバイトを無効化
- `send_codec_meta=false` - コーデック情報を無効化

結果として、**純粋なH.264/H.265ストリーム**がTCPソケットに流れる。

## 実装計画

### フェーズ1: 手動テスト（5分）

1. scrcpy-serverをデバイスにプッシュ
2. adb forwardでポートを開く
3. サーバーを起動
4. netcat または FFmpeg で接続してストリームを確認

```bash
# 1. サーバーをプッシュ
adb push scrcpy/scrcpy-server-v3.3.4 /data/local/tmp/scrcpy-server.jar

# 2. ポートフォワード
adb forward tcp:27183 localabstract:scrcpy_test

# 3. サーバー起動
adb shell CLASSPATH=/data/local/tmp/scrcpy-server.jar \
    app_process / com.genymobile.scrcpy.Server 3.3.4 \
    tunnel_forward=true \
    audio=false \
    control=false \
    cleanup=false \
    raw_stream=true \
    max_size=720 \
    max_fps=15 \
    video_bit_rate=2000000

# 4. 別ターミナルでFFmpegで受信
ffmpeg -f h264 -i tcp://localhost:27183 -c copy /tmp/test.mp4
```

### フェーズ2: Pythonクライアント実装（30分）

`backend/scrcpy_raw_client.py` を作成:

```python
import subprocess
import socket
import asyncio
from typing import AsyncIterator

class ScrcpyRawClient:
    """scrcpy-serverに直接接続してraw H.264ストリームを取得"""
    
    def __init__(
        self,
        device_serial: str,
        max_size: int = 720,
        max_fps: int = 15,
        video_bit_rate: int = 2_000_000,
        local_port: int = 27183,
    ):
        self.device_serial = device_serial
        self.max_size = max_size
        self.max_fps = max_fps
        self.video_bit_rate = video_bit_rate
        self.local_port = local_port
        self.socket_name = f"scrcpy_{id(self)}"
        self._process = None
        self._socket = None
    
    async def start(self) -> None:
        """サーバーを起動し接続"""
        # 1. サーバーjarをプッシュ（必要に応じて）
        await self._push_server()
        
        # 2. adb forward設定
        await self._setup_tunnel()
        
        # 3. サーバー起動
        await self._start_server()
        
        # 4. TCP接続
        await self._connect()
    
    async def read_stream(self) -> AsyncIterator[bytes]:
        """raw H.264チャンクを非同期で読み取り"""
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().create_connection(
            lambda: protocol, sock=self._socket
        )
        
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                break
            yield chunk
    
    async def stop(self) -> None:
        """クリーンアップ"""
        if self._socket:
            self._socket.close()
        if self._process:
            self._process.terminate()
        # adb forward --remove
```

### フェーズ3: FFmpegパイプライン統合（30分）

raw H.264をfMP4に変換してMedia Source Extensionsで再生:

```python
async def h264_to_fmp4_stream(h264_stream: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    """H.264をfMP4に変換"""
    proc = await asyncio.create_subprocess_exec(
        'ffmpeg',
        '-f', 'h264',
        '-i', 'pipe:0',
        '-c:v', 'copy',
        '-f', 'mp4',
        '-movflags', 'frag_keyframe+empty_moov+default_base_moof',
        'pipe:1',
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    
    async def writer():
        async for chunk in h264_stream:
            proc.stdin.write(chunk)
            await proc.stdin.drain()
        proc.stdin.close()
    
    asyncio.create_task(writer())
    
    while True:
        chunk = await proc.stdout.read(65536)
        if not chunk:
            break
        yield chunk
```

### フェーズ4: 既存バックエンドとの統合（30分）

`stream_session.py` を更新して新しいクライアントを使用。

## メリット

| 項目 | scrcpy CLI経由 | 直接サーバー接続 |
|------|---------------|-----------------|
| **シンプルさ** | プロセス管理が必要 | ソケット直接制御 |
| **レイテンシ** | プロセス間通信あり | 直接TCP |
| **フォーマット** | MKV/MP4ファイル | raw H.264ストリーム |
| **カスタマイズ** | CLIオプションに依存 | 柔軟なパラメータ |
| **リアルタイム** | 録画ファイル経由 | 即座にストリーム |

## リスク・懸念点

1. **プロトコル互換性**: scrcpy内部プロトコルはバージョン間で変わる可能性
   - 対策: サーバーバージョンを固定（v3.3.4）

2. **エラーハンドリング**: サーバー切断時のリカバリー
   - 対策: 再接続ロジックを実装

3. **複数デバイス**: 各デバイスに別ポートが必要
   - 対策: ポートプールを管理

## 結論

**方法Dは非常に実現可能！**

scrcpy-serverの `raw_stream=true` オプションにより、以下が不要:
- scrcpyクライアントのカスタマイズ
- パイプ出力の実装
- ファイル経由の録画

純粋なH.264ストリームを直接取得でき、FFmpegでfMP4に変換してブラウザ配信可能。

## 次のステップ

1. [x] 手動テストでストリーム取得を確認 ✅ 成功！169KB/5秒のH.264データ受信
2. [ ] Pythonクライアントの実装
3. [ ] 既存バックエンドとの統合
4. [ ] エラーハンドリングとリカバリー

## フェーズ1 テスト結果

```
Forward setup: 27183
Connected!
Received 169271 bytes total in 5 seconds
First 32 bytes (hex): 000000016742c0298d680b439a420c020c0f08846a0000000168ce01a835c800

ffprobe output:
Input #0, h264, from '/tmp/test_raw.h264':
  Duration: N/A, bitrate: N/A
  Stream #0:0: Video: h264 (Constrained Baseline), yuv420p, 720x448, 25 fps
```
