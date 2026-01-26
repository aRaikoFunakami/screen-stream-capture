"""WebSocket capture endpoints.

WS /api/ws/capture/{serial}

概要:
    WebSocket接続中、バックエンドはH.264デコーダを起動し、最新フレームを保持します。
    クライアントからのキャプチャリクエストに対し、その時点の画面をJPEGエンコードして返します。

仕様（重要）:
    - 最初のキャプチャは約0.5〜1秒かかる場合があります。
      これはデコーダ起動直後で、最初のフレームが来るまで待つ必要があるためです。
    - 2回目以降のキャプチャは約60〜120msで完了します。

Protocol (minimal):
- client -> server (text JSON): {"type":"capture","format":"jpeg","quality":80,"save":true}
- server -> client (text JSON): {"type":"capture_result",...}
- server -> client (binary): JPEG bytes

See work/multi_device_stream_and_capture/plan.md for details.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.capture_manager import CaptureManager
from app.services.device_manager import get_device_manager

logger = logging.getLogger(__name__)

router = APIRouter()


def _as_capture_result_dict(result: Any) -> dict[str, Any]:
    # Avoid importing pydantic for WS-only payload.
    return {
        "type": "capture_result",
        "capture_id": result.capture_id,
        "captured_at": result.captured_at,
        "serial": result.serial,
        "width": result.width,
        "height": result.height,
        "bytes": result.bytes,
        "path": result.path,
    }


@router.websocket("/ws/capture/{serial}")
async def websocket_capture(websocket: WebSocket, serial: str) -> None:
    """WebSocket 経由でサーバー側JPEGキャプチャを返す"""

    await websocket.accept()

    app = websocket.scope.get("app")
    capture_manager: CaptureManager | None = getattr(app.state, "capture_manager", None) if app else None
    if not capture_manager:
        await websocket.close(code=1011, reason="Server not ready")
        return

    worker_registry = getattr(app.state, "worker_registry", None) if app else None

    device_manager = get_device_manager()
    device = await device_manager.get_device(serial)
    if device is None:
        await websocket.close(code=4004, reason=f"Device {serial} not found")
        return

    worker = await capture_manager.acquire(serial)
    if worker_registry:
        await worker_registry.on_capture_connect(serial)
    logger.info(f"WebSocket capture started for {serial}")

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                break

            msg_type = data.get("type")
            if msg_type == "capture":
                fmt = (data.get("format") or "jpeg").lower()
                if fmt != "jpeg":
                    await websocket.send_json(
                        {
                            "type": "error",
                            "code": "UNSUPPORTED_FORMAT",
                            "message": f"format {fmt} is not supported",
                        }
                    )
                    continue

                quality = data.get("quality")
                save = bool(data.get("save", False))

                try:
                    result, jpeg = await worker.capture_jpeg(quality=quality, save=save)
                except TimeoutError:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "code": "CAPTURE_TIMEOUT",
                            "message": "Timed out waiting for a decoded frame",
                        }
                    )
                    continue
                except Exception as e:
                    await websocket.send_json(
                        {"type": "error", "code": "CAPTURE_FAILED", "message": str(e)}
                    )
                    continue

                await websocket.send_json(_as_capture_result_dict(result))
                await websocket.send_bytes(jpeg)

            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "BAD_REQUEST",
                        "message": "Unknown message type",
                    }
                )

    finally:
        await capture_manager.release(serial)
        if worker_registry:
            await worker_registry.on_capture_disconnect(serial)
        logger.info(f"WebSocket capture ended for {serial}")
