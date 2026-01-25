"""Screen Stream Capture Backend - FastAPI Application"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from device_manager import get_device_manager
from sse_manager import get_sse_manager
from stream_session import get_stream_manager
from h264_stream_session import get_h264_stream_manager

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def setup_device_change_notifier():
    """デバイス変更時に SSE で通知する設定"""
    device_manager = get_device_manager()
    sse_manager = get_sse_manager()
    
    def on_device_change():
        """デバイス変更時のコールバック"""
        asyncio.create_task(notify_device_change())
    
    async def notify_device_change():
        """デバイス一覧を SSE でブロードキャスト"""
        devices = await device_manager.list_devices()
        await sse_manager.broadcast("devices", [d.to_dict() for d in devices])
    
    device_manager.on_change(on_device_change)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションのライフサイクル管理"""
    # 起動時
    logger.info("Starting DeviceManager...")
    device_manager = get_device_manager()
    setup_device_change_notifier()
    await device_manager.start()
    
    yield
    
    # 終了時
    logger.info("Stopping services...")
    stream_manager = get_stream_manager()
    h264_manager = get_h264_stream_manager()
    await stream_manager.stop_all()
    await h264_manager.stop_all()
    await device_manager.stop()


app = FastAPI(
    title="Screen Stream Capture",
    description="Android デバイス画面ストリーミング & キャプチャシステム",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 設定（開発用：全許可）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz() -> dict:
    """ヘルスチェックエンドポイント"""
    return {
        "status": "ok",
        "version": "0.1.0",
    }


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
        # 接続時に現在のデバイス一覧を送信
        device_manager = get_device_manager()
        devices = await device_manager.list_devices()
        data = json.dumps([d.to_dict() for d in devices])
        yield f"event: devices\ndata: {data}\n\n"
        
        # 以降はブロードキャストを受信
        async for message in sse_manager.subscribe():
            yield message
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/stream/{serial}")
async def stream_device(serial: str):
    """デバイス画面のストリーミング（fMP4 形式）"""
    # デバイスの存在確認
    device_manager = get_device_manager()
    device = await device_manager.get_device(serial)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device {serial} not found")
    
    # ストリームセッションを取得または作成
    stream_manager = get_stream_manager()
    session = await stream_manager.get_or_create(serial)
    
    return StreamingResponse(
        session.subscribe(),
        media_type="video/mp4",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.websocket("/api/ws/stream/{serial}")
async def websocket_stream(websocket: WebSocket, serial: str):
    """WebSocket経由でraw H.264ストリームを送信
    
    JMuxer等のブラウザライブラリでデコードして再生
    """
    await websocket.accept()
    
    # デバイスの存在確認
    device_manager = get_device_manager()
    device = await device_manager.get_device(serial)
    if device is None:
        await websocket.close(code=4004, reason=f"Device {serial} not found")
        return
    
    logger.info(f"WebSocket H.264 stream started for {serial}")
    
    # H.264ストリームセッションを取得または作成
    h264_manager = get_h264_stream_manager()
    session = await h264_manager.get_or_create(serial)
    
    try:
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
