from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.router import api_router
from app.models.device import DeviceInfo, DeviceState
from app.services.capture_manager import CaptureManager


class _FakeStdin:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.writes.append(bytes(data))

    async def drain(self) -> None:
        return

    def close(self) -> None:
        self.closed = True


class _EOFStdout:
    async def read(self, n: int = -1) -> bytes:
        _ = n
        return b""


class _EOFStderr:
    async def readline(self) -> bytes:
        return b""


class _FakeProcess:
    def __init__(self) -> None:
        self.stdin = _FakeStdin()
        self.stdout = _EOFStdout()
        self.stderr = _EOFStderr()
        self.terminated = 0
        self.killed = 0
        self._waited = 0

    def terminate(self) -> None:
        self.terminated += 1

    def kill(self) -> None:
        self.killed += 1

    async def wait(self) -> int:
        self._waited += 1
        return 0


@dataclass
class _FakeSession:
    async def subscribe(self) -> AsyncIterator[bytes]:
        if False:  # pragma: no cover
            yield b""


class _FakeStreamManager:
    async def get_or_create(self, serial: str) -> _FakeSession:
        _ = serial
        return _FakeSession()


@pytest.mark.anyio
async def test_decoder_starts_only_on_first_acquire(monkeypatch: pytest.MonkeyPatch, tmp_path):
    # Track subprocess spawns.
    created: list[tuple[list[str], _FakeProcess]] = []

    async def _fake_create_subprocess_exec(*args, **kwargs):
        # The decoder uses stdin/stdout/stderr pipes.
        _ = kwargs
        proc = _FakeProcess()
        created.append(([str(a) for a in args], proc))
        return proc

    import app.services.capture_manager as cm

    monkeypatch.setattr(cm.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    mgr = CaptureManager(stream_manager=_FakeStreamManager(), output_dir=str(tmp_path), default_quality=80)

    # Before any acquire, nothing is running.
    assert await mgr.snapshot_running() == {}
    assert created == []

    w = await mgr.acquire("ABC")
    assert w.refcount == 1
    assert (await mgr.snapshot_running())["ABC"] is True

    # Decoder subprocess should be spawned exactly once.
    assert len(created) == 1
    argv, _proc = created[0]
    assert argv[0] == "ffmpeg"
    assert "-f" in argv and "h264" in argv
    assert "pipe:0" in argv and "pipe:1" in argv

    # Second acquire (same device) must not spawn another decoder.
    w2 = await mgr.acquire("ABC")
    assert w2 is w
    assert w.refcount == 2
    assert len(created) == 1

    # First release keeps decoder alive.
    await mgr.release("ABC")
    assert w.refcount == 1
    assert (await mgr.snapshot_running())["ABC"] is True
    assert created[0][1].terminated == 0

    # Final release stops decoder and removes worker.
    await mgr.release("ABC")
    assert await mgr.snapshot_running() == {}
    assert created[0][1].terminated == 1


def test_capture_ws_connection_controls_decoder_lifecycle(monkeypatch: pytest.MonkeyPatch, tmp_path):
    # This proves the WS endpoint acquires (starts decoder) on connect,
    # and releases (stops decoder) on disconnect.

    created: list[_FakeProcess] = []

    async def _fake_create_subprocess_exec(*args, **kwargs):
        _ = (args, kwargs)
        proc = _FakeProcess()
        created.append(proc)
        return proc

    import app.services.capture_manager as cm

    monkeypatch.setattr(cm.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    # Build a minimal app using the real capture endpoint + real CaptureManager.
    app = FastAPI()
    app.include_router(api_router)

    app.state.stream_manager = _FakeStreamManager()
    app.state.capture_manager = CaptureManager(
        stream_manager=app.state.stream_manager,
        output_dir=str(tmp_path),
        default_quality=80,
    )

    # Patch device lookup used by the endpoint.
    from app.api.endpoints import capture as capture_ep

    class _FakeDeviceManager:
        async def get_device(self, serial: str):
            if serial == "ABC123":
                return DeviceInfo(serial="ABC123", state=DeviceState.DEVICE)
            return None

    monkeypatch.setattr(capture_ep, "get_device_manager", lambda: _FakeDeviceManager())

    with TestClient(app) as client:
        assert created == []
        with client.websocket_connect("/api/ws/capture/ABC123"):
            # connect/disconnect only; no capture request required
            pass

    # Decoder was spawned during connect and terminated on disconnect.
    assert len(created) == 1
    assert created[0].terminated == 1
