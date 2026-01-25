"""Screen Stream Capture Backend - FastAPI Application

ライブラリ(pacakges/android-screen-stream)を利用し、以下のWeb APIを提供する公式バックエンド。

- デバイス管理 (DeviceManager, DeviceMonitor, DeviceRegistry)
- SSE によるリアルタイムデバイス通知 (/api/events)
- H.264 WebSocket ストリーミング (/api/ws/stream/{serial})

フロントエンドは examples/simple-viewer/frontend をサンプルとして提供する。
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from device_manager import get_device_manager
from sse_manager import get_sse_manager

from android_screen_stream import StreamConfig, StreamManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SCRCPY_SERVER_JAR = os.environ.get("SCRCPY_SERVER_JAR", "/app/vendor/scrcpy-server.jar")

stream_manager: StreamManager | None = None


def setup_device_change_notifier() -> None:
    """デバイス変更時に SSE で通知する設定"""
    device_manager = get_device_manager()
    sse_manager = get_sse_manager()

    def on_device_change() -> None:
        asyncio.create_task(notify_device_change())

    async def notify_device_change() -> None:
        devices = await device_manager.list_devices()
        await sse_manager.broadcast("devices", [d.to_dict() for d in devices])

    device_manager.on_change(on_device_change)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションのライフサイクル管理"""
    global stream_manager

    logger.info("Starting services...")
    logger.info(f"Using scrcpy-server.jar: {SCRCPY_SERVER_JAR}")

    device_manager = get_device_manager()
    setup_device_change_notifier()
    await device_manager.start()

    stream_manager = StreamManager(
        server_jar=SCRCPY_SERVER_JAR,
        default_config=StreamConfig.balanced(),
    )

    yield

    logger.info("Stopping services...")
    if stream_manager:
        await stream_manager.stop_all()
    await device_manager.stop()


app = FastAPI(
    title="Screen Stream Capture",
    description="Android デバイス画面ストリーミング & キャプチャシステム",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
@app.get("/api/healthz")
async def healthz() -> dict:
    """ヘルスチェックエンドポイント"""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/devices")
async def get_devices() -> list[dict]:
    """デバイス一覧を取得"""
    device_manager = get_device_manager()
    devices = await device_manager.list_devices()
    return [d.to_dict() for d in devices]


@app.get("/api/devices/{serial}")
async def get_device(serial: str) -> dict:
    """特定デバイスの情報を取得"""
    device_manager = get_device_manager()
    device = await device_manager.get_device(serial)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device {serial} not found")
    return device.to_dict()


@app.get("/api/events")
async def events():
    """SSE エンドポイント - デバイス変更をリアルタイム通知"""
    sse_manager = get_sse_manager()

    async def event_generator():
        device_manager = get_device_manager()
        devices = await device_manager.list_devices()
        data = json.dumps([d.to_dict() for d in devices])
        yield f"event: devices\ndata: {data}\n\n"

        async for message in sse_manager.subscribe():
            yield message

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.get("/api/sessions")
async def list_sessions():
    """アクティブなストリームセッション一覧"""
    if not stream_manager:
        return {"sessions": []}
    return {"sessions": stream_manager.active_sessions}


@app.websocket("/api/ws/stream/{serial}")
async def websocket_stream(websocket: WebSocket, serial: str):
    """WebSocket 経由で raw H.264 を送信"""
    await websocket.accept()

    if not stream_manager:
        await websocket.close(code=1011, reason="Server not ready")
        return

    device_manager = get_device_manager()
    device = await device_manager.get_device(serial)
    if device is None:
        await websocket.close(code=4004, reason=f"Device {serial} not found")
        return

    logger.info(f"WebSocket H.264 stream started for {serial}")

    try:
        session = await stream_manager.get_or_create(serial)
        async for chunk in session.subscribe():
            if not chunk:
                break
            await websocket.send_bytes(chunk)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for {serial}")
    except Exception as e:
        logger.error(f"WebSocket error for {serial}: {e}")
    finally:
        logger.info(f"WebSocket H.264 stream ended for {serial}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
