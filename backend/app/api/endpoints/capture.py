"""WebSocket capture endpoints.

WS /api/ws/capture/{serial}

概要:
    WebSocket接続中、バックエンドはH.264デコーダを起動し、最新フレームを保持します。
    クライアントからのキャプチャリクエストに対し、その時点の画面をJPEGエンコードして返します。

⚠️ 初期化待機時間（重要）:
    WebSocket接続後、最初のキャプチャリクエストを送信する前に **約6〜8秒の待機が必要** です。
    これはバックエンドがH.264デコーダ（ffmpeg）を起動し、最初のフレームをデコードするためです。
    
    待機せずにキャプチャリクエストを送信すると CAPTURE_TIMEOUT エラーが返されます。
    
    | タイミング                 | 所要時間      | 説明                              |
    |---------------------------|---------------|----------------------------------|
    | 接続〜初回キャプチャ可能     | 約6〜8秒      | デコーダ起動 + 最初のフレームデコード |
    | 2回目以降のキャプチャ       | 約60〜120ms   | デコード済みフレームのJPEGエンコード |

Protocol:
- client -> server (text JSON):
    {"type": "capture", "format": "jpeg", "quality": 80, "save": true}
    - type: "capture"（必須）
    - format: "jpeg"のみ対応（省略可、デフォルト: jpeg）
    - quality: 1-100（省略可、デフォルト: 環境変数 CAPTURE_JPEG_QUALITY または 80）
    - save: サーバーにも保存するか（省略可、デフォルト: false）

- server -> client (text JSON):
    {"type": "capture_result", "capture_id": "...", "width": 1080, "height": 1920, ...}

- server -> client (binary): JPEG bytes

エラーレスポンス:
    {"type": "error", "code": "UNSUPPORTED_FORMAT", "message": "..."}
    {"type": "error", "code": "CAPTURE_FAILED", "message": "..."}
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
