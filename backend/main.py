"""Screen Stream Capture Backend - FastAPI Application"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from device_manager import get_device_manager
from models import DeviceInfo
from websocket_manager import get_connection_manager

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def setup_device_change_notifier():
    """デバイス変更時に WebSocket で通知する設定"""
    device_manager = get_device_manager()
    connection_manager = get_connection_manager()
    
    def on_device_change():
        """デバイス変更時のコールバック"""
        asyncio.create_task(notify_device_change())
    
    async def notify_device_change():
        """デバイス一覧を WebSocket でブロードキャスト"""
        devices = await device_manager.list_devices()
        await connection_manager.broadcast({
            "type": "devices",
            "data": [d.to_dict() for d in devices],
        })
    
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


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket エンドポイント - デバイス変更をリアルタイム通知"""
    connection_manager = get_connection_manager()
    await connection_manager.connect(websocket)
    
    try:
        # 接続時に現在のデバイス一覧を送信
        device_manager = get_device_manager()
        devices = await device_manager.list_devices()
        await connection_manager.send_to(websocket, {
            "type": "devices",
            "data": [d.to_dict() for d in devices],
        })
        
        # 接続を維持（ping/pong）
        while True:
            try:
                data = await websocket.receive_text()
                # クライアントからのメッセージは今のところ無視
                logger.debug(f"Received from client: {data}")
            except WebSocketDisconnect:
                break
    finally:
        await connection_manager.disconnect(websocket)

