"""WebSocket streaming endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.device_manager import get_device_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/stream/{serial}")
async def websocket_stream(websocket: WebSocket, serial: str) -> None:
    """WebSocket 経由で raw H.264 を送信"""

    await websocket.accept()

    app = websocket.scope.get("app")
    stream_manager = getattr(app.state, "stream_manager", None) if app else None
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
