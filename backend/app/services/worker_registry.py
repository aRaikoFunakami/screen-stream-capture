"""Per-device worker registry for multi-client / multi-device management.

This service tracks how many WebSocket clients are connected per device for:
- stream WS (/api/ws/stream/{serial})
- capture WS (/api/ws/capture/{serial})

It is responsible for idling out stream sessions when there are no clients.
The underlying video ingest is handled by android-screen-stream's StreamManager.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from android_screen_stream import StreamManager


@dataclass
class DeviceWorkerState:
    serial: str
    stream_clients: int = 0
    capture_clients: int = 0
    last_activity: str = ""
    idle_stop_task: Optional[asyncio.Task[None]] = None


class WorkerRegistry:
    def __init__(self, *, stream_manager: "StreamManager", idle_timeout_sec: float) -> None:
        self._stream_manager = stream_manager
        self._idle_timeout_sec = float(idle_timeout_sec)

        self._lock = asyncio.Lock()
        self._states: dict[str, DeviceWorkerState] = {}

    async def on_stream_connect(self, serial: str) -> None:
        async with self._lock:
            st = self._states.get(serial)
            if st is None:
                st = DeviceWorkerState(serial=serial)
                self._states[serial] = st

            st.stream_clients += 1
            st.last_activity = datetime.now(timezone.utc).isoformat()
            if st.idle_stop_task:
                st.idle_stop_task.cancel()
                st.idle_stop_task = None

    async def on_stream_disconnect(self, serial: str) -> None:
        async with self._lock:
            st = self._states.get(serial)
            if st is None:
                return

            st.stream_clients = max(0, st.stream_clients - 1)
            st.last_activity = datetime.now(timezone.utc).isoformat()

            await self._schedule_idle_stop_locked(st)

    async def on_capture_connect(self, serial: str) -> None:
        async with self._lock:
            st = self._states.get(serial)
            if st is None:
                st = DeviceWorkerState(serial=serial)
                self._states[serial] = st

            st.capture_clients += 1
            st.last_activity = datetime.now(timezone.utc).isoformat()
            if st.idle_stop_task:
                st.idle_stop_task.cancel()
                st.idle_stop_task = None

    async def on_capture_disconnect(self, serial: str) -> None:
        async with self._lock:
            st = self._states.get(serial)
            if st is None:
                return

            st.capture_clients = max(0, st.capture_clients - 1)
            st.last_activity = datetime.now(timezone.utc).isoformat()

            await self._schedule_idle_stop_locked(st)

    async def _schedule_idle_stop_locked(self, st: DeviceWorkerState) -> None:
        if st.stream_clients != 0 or st.capture_clients != 0:
            return

        if st.idle_stop_task:
            st.idle_stop_task.cancel()

        st.idle_stop_task = asyncio.create_task(self._idle_stop(st.serial))

    async def _idle_stop(self, serial: str) -> None:
        try:
            await asyncio.sleep(self._idle_timeout_sec)
            await self._stream_manager.stop_session(serial)
        finally:
            async with self._lock:
                st = self._states.get(serial)
                if st and st.stream_clients == 0 and st.capture_clients == 0:
                    st.idle_stop_task = None

    async def snapshot(self) -> list[DeviceWorkerState]:
        async with self._lock:
            return [
                DeviceWorkerState(
                    serial=s.serial,
                    stream_clients=s.stream_clients,
                    capture_clients=s.capture_clients,
                    last_activity=s.last_activity,
                    idle_stop_task=None,
                )
                for s in self._states.values()
            ]


_worker_registry: Optional[WorkerRegistry] = None


def get_worker_registry(*, stream_manager: "StreamManager", idle_timeout_sec: float) -> WorkerRegistry:
    global _worker_registry
    if _worker_registry is None:
        _worker_registry = WorkerRegistry(stream_manager=stream_manager, idle_timeout_sec=idle_timeout_sec)
    return _worker_registry
