"""WS /api/ws/control/{serial} が CONTROL_TOKEN 未設定・不一致の接続を拒否することのテスト(端末不要)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.endpoints import control


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(control.router, prefix="/api")
    return TestClient(app)


@pytest.mark.parametrize("env, first", [
    (None, {"type": "auth", "token": "x"}),          # CONTROL_TOKEN 未設定なら常に拒否
    ("right", {"type": "auth", "token": "wrong"}),
    ("right", {"type": "pointer"}),
])
def test_control_rejects_without_valid_token(client, monkeypatch, env, first):
    if env is None:
        monkeypatch.delenv("CONTROL_TOKEN", raising=False)
    else:
        monkeypatch.setenv("CONTROL_TOKEN", env)
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/api/ws/control/emulator-5554") as ws:
            ws.send_json(first)
            ws.receive_text()
    assert e.value.code == 4403
