from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect


def test_ws_stream_sends_h264_chunks(client):
    with client.websocket_connect("/api/ws/stream/ABC123") as ws:
        assert ws.receive_bytes() == b"chunk1"
        assert ws.receive_bytes() == b"chunk2"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_bytes()


def test_ws_stream_unknown_device_closes(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/ws/stream/NOPE") as ws:
            ws.receive_bytes()
    assert exc.value.code == 4004
