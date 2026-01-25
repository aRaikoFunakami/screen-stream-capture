"""Screen Stream Capture Backend - FastAPI Application"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from device_manager import get_device_manager
from sse_manager import get_sse_manager

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
    logger.info("Stopping DeviceManager...")
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

