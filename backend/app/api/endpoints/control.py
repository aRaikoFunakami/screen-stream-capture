"""WebSocket control endpoint (client → device input).

WS /api/ws/control/{serial}

概要:
    配信(/api/ws/stream)とは別の、端末を操作するためのチャネル。受け取った JSON の制御メッセージを
    android_screen_stream.ScrcpyControlClient(映像なしの操作専用 scrcpy)で端末へ注入する。
    配信より強い権限なので、ブラウザから直接ではなく、認可済みの呼び出し元(UI backend)からだけ使う想定。

認証:
    環境変数 CONTROL_TOKEN が未設定ならこのエンドポイントは使えない(4403)。設定時は接続直後の最初のメッセージで
    {"type": "auth", "token": <CONTROL_TOKEN>} を送らせ、5 秒以内に一致しなければ 4403 で切る。
    (トークンを URL に載せるとアクセスログに残るため、最初のメッセージで受ける)

Protocol:
- client -> server (text): {"type": "auth", ...} の後に pointer / wheel / key / text の制御メッセージ
  (android_screen_stream.control の docstring を参照。web-screen-stream と同じ形)
- server -> client (text): {"type": "ready"} の後、各メッセージに {"type": "ack"|"error", "seq": ...}

エラー:
- 4403: 認証失敗 / CONTROL_TOKEN 未設定
- 4004: Device not found
- 4009: 同じ端末を既に誰かが操作している
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from android_screen_stream import ScrcpyControlClient

from app.services.device_manager import get_device_manager

logger = logging.getLogger(__name__)

router = APIRouter()

AUTH_TIMEOUT = 5.0
_controlling: set[str] = set()  # 操作中の serial(同じ端末を同時に 1 接続だけ)


async def _authenticate(websocket: WebSocket, expected: str) -> bool:
    try:
        first = json.loads(await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT))
    except (asyncio.TimeoutError, json.JSONDecodeError, KeyError, WebSocketDisconnect):
        return False
    token = first.get("token") if isinstance(first, dict) and first.get("type") == "auth" else None
    return isinstance(token, str) and secrets.compare_digest(token.encode(), expected.encode())


@router.websocket("/ws/control/{serial}")
async def websocket_control(websocket: WebSocket, serial: str) -> None:
    await websocket.accept()
    expected = os.environ.get("CONTROL_TOKEN", "")
    if not expected or not await _authenticate(websocket, expected):
        await websocket.close(code=4403, reason="Forbidden")
        return
    if await get_device_manager().get_device(serial) is None:
        await websocket.close(code=4004, reason=f"Device {serial} not found")
        return
    if serial in _controlling:
        await websocket.close(code=4009, reason="Device is already being controlled")
        return
    _controlling.add(serial)
    client: ScrcpyControlClient | None = None
    try:
        client = ScrcpyControlClient(serial, websocket.app.state.settings.scrcpy_server_jar)
        await client.start()
        await websocket.send_json({"type": "ready"})
        while True:
            try:
                raw = json.loads(await websocket.receive_text())
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "seq": None, "error": "invalid JSON"})
                continue
            await websocket.send_json(await client.handle(raw))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("control channel error for %s", serial)
        try:
            await websocket.close(code=1011, reason="control channel error")
        except RuntimeError:
            pass
    finally:
        _controlling.discard(serial)
        if client:
            await client.stop()
