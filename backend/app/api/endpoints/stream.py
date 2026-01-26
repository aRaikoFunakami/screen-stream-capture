"""WebSocket streaming endpoints.

WS /api/ws/stream/{serial}

概要:
    WebSocket接続すると、指定デバイスのH.264ストリームをバイナリで受信できます。
    接続中はscrcpy-serverが起動し、切断で自動停止します（最後の購読者が切断後、
    STREAM_IDLE_TIMEOUT_SEC秒でセッション終了）。

Protocol:
- client -> server: なし（受信専用）
- server -> client (binary): H.264 NAL units（Annex-B形式、0x00000001区切り）

フロントエンド実装例:
    JMuxer等でH.264をMSE経由で<video>に表示できます。
    画面回転時はSPS/PPSが変更されるため、JMuxerのリセットが必要です。

エラー:
- 4004: Device not found
- 1011: Server not ready
"""

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

    worker_registry = getattr(app.state, "worker_registry", None) if app else None

    device_manager = get_device_manager()
    device = await device_manager.get_device(serial)
    if device is None:
        await websocket.close(code=4004, reason=f"Device {serial} not found")
        return

    logger.info(f"WebSocket H.264 stream started for {serial}")

    if worker_registry:
        await worker_registry.on_stream_connect(serial)

    try:
        session = await stream_manager.get_or_create(serial)
        async for chunk in session.subscribe():
            if not chunk:
                break
            await websocket.send_bytes(chunk)

        # If the session ends (e.g., upstream stopped), proactively close so
        # clients don't hang waiting for more frames.
        try:
            await websocket.close(code=1000)
        except Exception:
            # If already closed/disconnected, ignore.
            pass

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for {serial}")
    except Exception as e:
        logger.error(f"WebSocket error for {serial}: {e}")
    finally:
        if worker_registry:
            await worker_registry.on_stream_disconnect(serial)
        logger.info(f"WebSocket H.264 stream ended for {serial}")
