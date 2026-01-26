from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.endpoints import healthz
from app.api.router import api_router
from app.models.device import DeviceInfo, DeviceState


@dataclass
class _WorkerState:
    serial: str
    stream_clients: int = 0
    capture_clients: int = 0


class FakeWorkerRegistry:
    def __init__(self) -> None:
        self._states: dict[str, _WorkerState] = {}

    async def on_stream_connect(self, serial: str) -> None:
        st = self._states.setdefault(serial, _WorkerState(serial=serial))
        st.stream_clients += 1

    async def on_stream_disconnect(self, serial: str) -> None:
        st = self._states.setdefault(serial, _WorkerState(serial=serial))
        st.stream_clients = max(0, st.stream_clients - 1)

    async def on_capture_connect(self, serial: str) -> None:
        st = self._states.setdefault(serial, _WorkerState(serial=serial))
        st.capture_clients += 1

    async def on_capture_disconnect(self, serial: str) -> None:
        st = self._states.setdefault(serial, _WorkerState(serial=serial))
        st.capture_clients = max(0, st.capture_clients - 1)

    async def snapshot(self) -> list[_WorkerState]:
        return list(self._states.values())


class FakeStreamSession:
    def __init__(self, *, chunks: list[bytes] | None = None) -> None:
        self.is_running = True
        self.subscriber_count = 0
        self._chunks = chunks or []

    async def subscribe(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


class FakeStreamManager:
    def __init__(self) -> None:
        self._sessions: dict[str, FakeStreamSession] = {}

    @property
    def active_sessions(self) -> list[str]:
        return list(self._sessions.keys())

    def set_session(self, serial: str, session: FakeStreamSession) -> None:
        self._sessions[serial] = session

    def get_session(self, serial: str) -> FakeStreamSession | None:
        return self._sessions.get(serial)

    async def get_or_create(self, serial: str) -> FakeStreamSession:
        return self._sessions.setdefault(serial, FakeStreamSession())


@dataclass
class FakeCaptureResult:
    capture_id: str
    captured_at: str
    serial: str
    width: int
    height: int
    bytes: int
    path: str | None


class FakeCaptureWorker:
    def __init__(self, *, serial: str, jpeg_bytes: bytes) -> None:
        self._serial = serial
        self._jpeg_bytes = jpeg_bytes

    async def capture_jpeg(self, *, quality: int | None = None, save: bool = False):
        _ = quality
        path = "/tmp/fake.jpg" if save else None
        result = FakeCaptureResult(
            capture_id="cap_1",
            captured_at=datetime.now(timezone.utc).isoformat(),
            serial=self._serial,
            width=1280,
            height=720,
            bytes=len(self._jpeg_bytes),
            path=path,
        )
        return result, self._jpeg_bytes


class FakeCaptureManager:
    def __init__(self, *, jpeg_bytes: bytes) -> None:
        self._jpeg_bytes = jpeg_bytes
        self._acquired: dict[str, int] = {}
        self._running: dict[str, bool] = {}

    async def acquire(self, serial: str) -> FakeCaptureWorker:
        self._acquired[serial] = self._acquired.get(serial, 0) + 1
        self._running[serial] = True
        return FakeCaptureWorker(serial=serial, jpeg_bytes=self._jpeg_bytes)

    async def release(self, serial: str) -> None:
        self._acquired[serial] = max(0, self._acquired.get(serial, 0) - 1)
        if self._acquired.get(serial, 0) == 0:
            self._running[serial] = False

    async def snapshot_running(self) -> dict[str, bool]:
        return dict(self._running)


class FakeDeviceManager:
    def __init__(self, devices: list[DeviceInfo]) -> None:
        self._devices = {d.serial: d for d in devices}

    async def list_devices(self) -> list[DeviceInfo]:
        return list(self._devices.values())

    async def get_device(self, serial: str) -> DeviceInfo | None:
        return self._devices.get(serial)


class FakeSSEManager:
    def __init__(self, *, next_message: str | None = None) -> None:
        self._next_message = next_message

    async def subscribe(self):
        # yield at most 1 message to let tests finish
        if self._next_message is not None:
            yield self._next_message


@pytest.fixture
def test_devices() -> list[DeviceInfo]:
    return [
        DeviceInfo(
            serial="ABC123",
            state=DeviceState.DEVICE,
            model="Pixel",
            manufacturer="Google",
            is_emulator=False,
            last_seen=datetime(2026, 1, 26, tzinfo=timezone.utc),
        )
    ]


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, test_devices: list[DeviceInfo]) -> FastAPI:
    # Build an app without the production lifespan (no adb/scrcpy/ffmpeg).
    app = FastAPI()
    app.include_router(healthz.router, tags=["health"])
    app.include_router(api_router)

    # State-based services
    stream_manager = FakeStreamManager()
    stream_manager.set_session("ABC123", FakeStreamSession(chunks=[b"chunk1", b"chunk2"]))
    app.state.stream_manager = stream_manager

    app.state.worker_registry = FakeWorkerRegistry()
    app.state.capture_manager = FakeCaptureManager(jpeg_bytes=b"\xff\xd8FAKEJPEG\xff\xd9")

    # Patch singleton accessors imported into endpoint modules.
    from app.api.endpoints import capture as capture_ep
    from app.api.endpoints import devices as devices_ep
    from app.api.endpoints import events as events_ep
    from app.api.endpoints import stream as stream_ep

    fake_device_manager = FakeDeviceManager(test_devices)
    fake_sse_manager = FakeSSEManager(next_message="event: ping\ndata: {}\n\n")

    monkeypatch.setattr(devices_ep, "get_device_manager", lambda: fake_device_manager)
    monkeypatch.setattr(events_ep, "get_device_manager", lambda: fake_device_manager)
    monkeypatch.setattr(stream_ep, "get_device_manager", lambda: fake_device_manager)
    monkeypatch.setattr(capture_ep, "get_device_manager", lambda: fake_device_manager)
    monkeypatch.setattr(events_ep, "get_sse_manager", lambda: fake_sse_manager)

    return app


@pytest.fixture
def client(app: FastAPI):
    # Ensure background threads started by TestClient are properly stopped.
    with TestClient(app) as c:
        yield c
