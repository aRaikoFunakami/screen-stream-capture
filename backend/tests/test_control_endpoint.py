"""WS /api/ws/control/{serial} の認証・端末確認・排他のテスト(端末不要)."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.endpoints import control

URL = "/api/ws/control/emulator-5554"


class _Devices:
    def __init__(self, known):
        self.known = known

    async def get_device(self, serial):
        return object() if serial in self.known else None


class _FakeClient:
    def __init__(self, serial, jar):
        self.stopped = False

    async def start(self):
        pass

    async def handle(self, raw):
        return {"type": "ack", "seq": raw.get("seq"), "ok": True}

    async def stop(self):
        self.stopped = True


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(control, "get_device_manager", lambda: _Devices({"emulator-5554"}))
    monkeypatch.setattr(control, "ScrcpyControlClient", _FakeClient)
    app = FastAPI()
    app.state.settings = SimpleNamespace(scrcpy_server_jar="unused.jar")
    app.include_router(control.router, prefix="/api")
    return TestClient(app)


def _closed_code(client, first=None):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(URL) as ws:
            if first is not None:
                ws.send_json(first)
            ws.receive_text()
    return e.value.code


def test_closed_immediately_when_token_unset(client, monkeypatch):
    monkeypatch.delenv("CONTROL_TOKEN", raising=False)
    assert _closed_code(client) == 4403  # auth を送らなくても待たずに閉じる


@pytest.mark.parametrize("first", [
    {"type": "auth", "token": "wrong"},
    {"type": "auth", "token": "ひみつ"},  # ASCII 以外でも例外にならず拒否
    {"type": "auth"},
    {"type": "pointer", "action": "down", "x": 0.5, "y": 0.5},  # auth なし
])
def test_rejects_bad_or_missing_auth(client, monkeypatch, first):
    monkeypatch.setenv("CONTROL_TOKEN", "right")
    assert _closed_code(client, first) == 4403


def test_unknown_device_is_4004(client, monkeypatch):
    monkeypatch.setenv("CONTROL_TOKEN", "right")
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/api/ws/control/nope") as ws:
            ws.send_json({"type": "auth", "token": "right"})
            ws.receive_text()
    assert e.value.code == 4004


def test_ready_ack_and_second_controller_is_4009(client, monkeypatch):
    monkeypatch.setenv("CONTROL_TOKEN", "right")
    monkeypatch.setattr(control, "SLOT_WAIT", 0.2)
    with client.websocket_connect(URL) as ws:
        ws.send_json({"type": "auth", "token": "right"})
        assert ws.receive_json() == {"type": "ready"}
        ws.send_json({"type": "key", "key": "Enter", "seq": 1})
        assert ws.receive_json() == {"type": "ack", "seq": 1, "ok": True}
        ws.send_text("not json")
        assert ws.receive_json()["type"] == "error"
        assert _closed_code(client, {"type": "auth", "token": "right"}) == 4009
    # 切断後は同じ端末をまた操作できる
    with client.websocket_connect(URL) as ws:
        ws.send_json({"type": "auth", "token": "right"})
        assert ws.receive_json() == {"type": "ready"}


def test_idle_connection_is_closed_and_device_released(client, monkeypatch):
    monkeypatch.setenv("CONTROL_TOKEN", "right")
    monkeypatch.setattr(control, "IDLE_TIMEOUT", 0.2)
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(URL) as ws:
            ws.send_json({"type": "auth", "token": "right"})
            assert ws.receive_json() == {"type": "ready"}
            ws.receive_text()
    assert e.value.code == 1000
    assert "emulator-5554" not in control._controlling
