from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect


def test_ws_capture_happy_path(client):
    with client.websocket_connect("/api/ws/capture/ABC123") as ws:
        ws.send_json({"type": "capture", "format": "jpeg", "quality": 80, "save": False})
        msg = ws.receive_json()
        assert msg["type"] == "capture_result"
        assert msg["serial"] == "ABC123"
        assert msg["bytes"] > 0
        assert msg["width"] == 1280
        assert msg["height"] == 720

        jpeg = ws.receive_bytes()
        assert jpeg.startswith(b"\xff\xd8")
        assert jpeg.endswith(b"\xff\xd9")

        ws.send_json({"type": "unknown"})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "BAD_REQUEST"


def test_ws_capture_unsupported_format(client):
    with client.websocket_connect("/api/ws/capture/ABC123") as ws:
        ws.send_json({"type": "capture", "format": "png"})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "UNSUPPORTED_FORMAT"


def test_ws_capture_unknown_device_closes(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/ws/capture/NOPE") as ws:
            ws.send_json({"type": "capture"})
            ws.receive_json()
    assert exc.value.code == 4004
