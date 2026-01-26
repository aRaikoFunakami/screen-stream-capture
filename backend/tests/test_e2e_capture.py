"""総合テスト: 実際のデバイスを使ったキャプチャ機能のE2Eテスト

このテストは実際の Android デバイス（実機またはエミュレータ）を使用して、
以下のパイプラインが正常に動作することを検証します：

1. adb でデバイスに接続
2. scrcpy-server を起動して H.264 ストリームを取得
3. ffmpeg で H.264 → rawvideo (yuv420p) にデコード
4. rawvideo から JPEG を生成

前提条件:
- adb devices で少なくとも1台のデバイスが接続されていること
- scrcpy-server.jar が vendor/ に存在すること
- ffmpeg がインストールされていること

実行方法:
    cd backend
    uv run pytest tests/test_e2e_capture.py -v -s
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import create_app


def get_connected_devices() -> list[str]:
    """adb devices で接続中のデバイスシリアルを取得"""
    result = subprocess.run(
        ["adb", "devices"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    lines = result.stdout.strip().split("\n")[1:]  # ヘッダーをスキップ
    devices = []
    for line in lines:
        if "\tdevice" in line:
            serial = line.split("\t")[0]
            devices.append(serial)
    return devices


@pytest.fixture(scope="module")
def connected_device() -> str:
    """テスト用デバイスのシリアルを取得（なければスキップ）"""
    devices = get_connected_devices()
    if not devices:
        pytest.skip("No Android device connected. Run 'adb devices' to check.")
    return devices[0]


@pytest.fixture(scope="module")
def app():
    """実際のアプリケーションインスタンス"""
    return create_app()


@pytest.fixture(scope="module")
def test_client(app):
    """TestClient with lifespan（デバイスマネージャー等が起動した状態）"""
    from starlette.testclient import TestClient
    with TestClient(app) as client:
        yield client


@pytest.fixture
async def client(app):
    """AsyncClient for testing"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_healthz(client: AsyncClient) -> None:
    """ヘルスチェックエンドポイントが応答すること"""
    response = await client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_list_devices(test_client, connected_device: str) -> None:
    """デバイス一覧に接続中のデバイスが含まれること"""
    import time
    # デバイスマネージャーの初期化を待つ
    time.sleep(2.0)
    
    response = test_client.get("/api/devices")
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    
    serials = [d["serial"] for d in data]
    assert connected_device in serials


def test_capture_jpeg_via_websocket(
    test_client,
    connected_device: str,
) -> None:
    """WebSocket 経由で JPEG キャプチャが取得できること"""
    import time
    
    # デバイスマネージャーの初期化を待つ
    time.sleep(2.0)
    
    # キャプチャ WebSocket に接続
    with test_client.websocket_connect(f"/api/ws/capture/{connected_device}") as ws:
        # scrcpy 起動と ffmpeg デコードを待つ
        time.sleep(5.0)
        
        # キャプチャリクエストを送信
        ws.send_json({
            "type": "capture",
            "format": "jpeg",
            "quality": 80,
            "save": False,
        })
        
        # メタデータを受信（最大60秒待機）
        result = None
        for _ in range(60):
            try:
                msg = ws.receive_json()
                if msg.get("type") == "capture_result":
                    result = msg
                    break
                elif msg.get("type") == "error":
                    pytest.fail(f"Capture error: {msg}")
            except Exception as e:
                print(f"Waiting for response: {e}")
                time.sleep(1.0)
        
        assert result is not None, "Did not receive capture_result"
        assert result["serial"] == connected_device
        assert result["width"] > 0
        assert result["height"] > 0
        assert result["bytes"] > 0
        
        # JPEG バイナリを受信
        jpeg_bytes = ws.receive_bytes()
        
        # JPEG フォーマットの検証
        assert jpeg_bytes.startswith(b"\xff\xd8"), "Should start with JPEG SOI marker"
        assert jpeg_bytes.endswith(b"\xff\xd9"), "Should end with JPEG EOI marker"
        assert len(jpeg_bytes) == result["bytes"]
        
        print(f"✅ Captured JPEG: {result['width']}x{result['height']}, {len(jpeg_bytes)} bytes")


def test_capture_jpeg_saves_to_file(
    test_client,
    connected_device: str,
    tmp_path: Path,
) -> None:
    """JPEG キャプチャがファイルに保存されること"""
    import time
    
    # キャプチャ WebSocket に接続
    with test_client.websocket_connect(f"/api/ws/capture/{connected_device}") as ws:
        # scrcpy 起動と ffmpeg デコードを待つ
        time.sleep(5.0)
        
        ws.send_json({
            "type": "capture",
            "format": "jpeg",
            "quality": 90,
            "save": True,
        })
        
        result = None
        for _ in range(60):
            try:
                msg = ws.receive_json()
                if msg.get("type") == "capture_result":
                    result = msg
                    break
                elif msg.get("type") == "error":
                    pytest.fail(f"Capture error: {msg}")
            except Exception as e:
                print(f"Waiting for response: {e}")
                time.sleep(1.0)
        
        assert result is not None, "Did not receive capture_result"
        assert result["path"] is not None, "Path should be set when save=True"
        
        # ファイルが存在することを確認
        saved_path = Path(result["path"])
        assert saved_path.exists(), f"Saved file should exist: {saved_path}"
        
        # JPEG バイナリも受信
        jpeg_bytes = ws.receive_bytes()
        
        # 保存されたファイルの内容が一致することを確認
        saved_bytes = saved_path.read_bytes()
        assert saved_bytes == jpeg_bytes
        
        print(f"✅ Saved JPEG to: {saved_path}, {len(jpeg_bytes)} bytes")


def test_stream_websocket_receives_h264(
    test_client,
    connected_device: str,
) -> None:
    """Stream WebSocket で H.264 データを受信できること"""
    import time
    
    with test_client.websocket_connect(f"/api/ws/stream/{connected_device}") as ws:
        # H.264 データを受信
        total_bytes = 0
        chunks_received = 0
        
        for _ in range(10):  # 10チャンクまで受信
            try:
                data = ws.receive_bytes()
                total_bytes += len(data)
                chunks_received += 1
                
                if chunks_received >= 5:
                    break
            except Exception:
                time.sleep(0.5)
        
        assert chunks_received >= 1, "Should receive at least 1 H.264 chunk"
        assert total_bytes > 0, "Should receive H.264 data"
        
        print(f"✅ Received H.264: {chunks_received} chunks, {total_bytes} bytes")


def test_multiple_devices_capture(test_client) -> None:
    """複数デバイスが接続されている場合、両方からキャプチャできること"""
    import time
    
    devices = get_connected_devices()
    if len(devices) < 2:
        pytest.skip("Need at least 2 devices for this test")
    
    results = {}
    
    for device in devices[:2]:  # 最大2台
        with test_client.websocket_connect(f"/api/ws/capture/{device}") as ws:
            # scrcpy 起動と ffmpeg デコードを待つ
            time.sleep(5.0)
            
            ws.send_json({
                "type": "capture",
                "format": "jpeg",
                "quality": 80,
                "save": False,
            })
            
            result = None
            for _ in range(60):
                try:
                    msg = ws.receive_json()
                    if msg.get("type") == "capture_result":
                        result = msg
                        break
                    elif msg.get("type") == "error":
                        pytest.fail(f"Capture error for {device}: {msg}")
                except Exception:
                    time.sleep(1.0)
            
            if result:
                jpeg_bytes = ws.receive_bytes()
                results[device] = {
                    "width": result["width"],
                    "height": result["height"],
                    "bytes": len(jpeg_bytes),
                }
                print(f"✅ {device}: {result['width']}x{result['height']}, {len(jpeg_bytes)} bytes")
    
    assert len(results) == 2, f"Should capture from 2 devices, got {len(results)}"
