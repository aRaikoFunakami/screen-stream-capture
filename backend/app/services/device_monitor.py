"""ADB デバイスモニター - track-devices によるイベント駆動監視"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from app.models.device import DeviceState

logger = logging.getLogger(__name__)


class DeviceMonitor:
    """adb track-devices を購読し、デバイス変更イベントを発行"""

    def __init__(self):
        self._process: Optional[asyncio.subprocess.Process] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

        self._on_connected: list[Callable[[str, DeviceState], None]] = []
        self._on_disconnected: list[Callable[[str], None]] = []
        self._on_state_changed: list[Callable[[str, DeviceState], None]] = []

        self._current_devices: dict[str, DeviceState] = {}

    def on_device_connected(self, callback: Callable[[str, DeviceState], None]) -> None:
        self._on_connected.append(callback)

    def on_device_disconnected(self, callback: Callable[[str], None]) -> None:
        self._on_disconnected.append(callback)

    def on_state_changed(self, callback: Callable[[str, DeviceState], None]) -> None:
        self._on_state_changed.append(callback)

    async def start(self) -> None:
        if self._running:
            logger.warning("DeviceMonitor is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("DeviceMonitor started")

    async def stop(self) -> None:
        self._running = False

        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
            except ProcessLookupError:
                pass
            self._process = None

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("DeviceMonitor stopped")

    async def _monitor_loop(self) -> None:
        while self._running:
            try:
                await self._run_track_devices()
            except Exception as e:
                logger.error(f"Error in track-devices: {e}")
                if self._running:
                    await asyncio.sleep(2.0)

    async def _run_track_devices(self) -> None:
        self._process = await asyncio.create_subprocess_exec(
            "adb",
            "track-devices",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        logger.info("Started adb track-devices")

        try:
            while self._running and self._process.stdout:
                length_hex = await self._process.stdout.read(4)
                if not length_hex:
                    break

                try:
                    length = int(length_hex.decode(), 16)
                except ValueError:
                    logger.error(f"Invalid length prefix: {length_hex}")
                    continue

                if length == 0:
                    await self._process_device_list("")
                    continue

                data = await self._process.stdout.read(length)
                if not data:
                    break

                await self._process_device_list(data.decode().strip())

        finally:
            if self._process:
                self._process.terminate()
                await self._process.wait()

    async def _process_device_list(self, data: str) -> None:
        new_devices: dict[str, DeviceState] = {}

        for line in data.split("\n"):
            line = line.strip()
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) >= 2:
                serial = parts[0]
                state_str = parts[1]
                state = self._parse_state(state_str)
                new_devices[serial] = state

        old_serials = set(self._current_devices.keys())
        new_serials = set(new_devices.keys())

        for serial in new_serials - old_serials:
            state = new_devices[serial]
            logger.info(f"Device connected: {serial} ({state.value})")
            for callback in self._on_connected:
                try:
                    callback(serial, state)
                except Exception as e:
                    logger.error(f"Error in on_connected callback: {e}")

        for serial in old_serials - new_serials:
            logger.info(f"Device disconnected: {serial}")
            for callback in self._on_disconnected:
                try:
                    callback(serial)
                except Exception as e:
                    logger.error(f"Error in on_disconnected callback: {e}")

        for serial in old_serials & new_serials:
            old_state = self._current_devices[serial]
            new_state = new_devices[serial]
            if old_state != new_state:
                logger.info(f"Device state changed: {serial} {old_state.value} -> {new_state.value}")
                for callback in self._on_state_changed:
                    try:
                        callback(serial, new_state)
                    except Exception as e:
                        logger.error(f"Error in on_state_changed callback: {e}")

        self._current_devices = new_devices

    def _parse_state(self, state_str: str) -> DeviceState:
        state_map = {
            "device": DeviceState.DEVICE,
            "offline": DeviceState.OFFLINE,
            "unauthorized": DeviceState.UNAUTHORIZED,
            "connecting": DeviceState.CONNECTING,
        }
        return state_map.get(state_str.lower(), DeviceState.UNKNOWN)

    def get_current_devices(self) -> dict[str, DeviceState]:
        return self._current_devices.copy()
