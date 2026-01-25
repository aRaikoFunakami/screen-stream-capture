"""デバイスレジストリ - デバイス情報のキャッシュと管理"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from app.models.device import DeviceInfo, DeviceState

logger = logging.getLogger(__name__)


class DeviceRegistry:
    """デバイス情報を管理するレジストリ"""

    def __init__(self):
        self._devices: dict[str, DeviceInfo] = {}
        self._lock = asyncio.Lock()

    async def register(self, serial: str, state: DeviceState) -> DeviceInfo:
        async with self._lock:
            if serial in self._devices:
                device = self._devices[serial]
                device.state = state
                device.last_seen = datetime.now()
            else:
                device = DeviceInfo(
                    serial=serial,
                    state=state,
                    is_emulator=self._is_emulator(serial),
                )
                self._devices[serial] = device

                if state == DeviceState.DEVICE:
                    asyncio.create_task(self._fetch_device_details(serial))

            return device

    async def unregister(self, serial: str) -> Optional[DeviceInfo]:
        async with self._lock:
            return self._devices.pop(serial, None)

    async def update_state(self, serial: str, state: DeviceState) -> Optional[DeviceInfo]:
        async with self._lock:
            if serial in self._devices:
                device = self._devices[serial]
                device.state = state
                device.last_seen = datetime.now()

                if state == DeviceState.DEVICE and not device.model:
                    asyncio.create_task(self._fetch_device_details(serial))

                return device
            return None

    async def get(self, serial: str) -> Optional[DeviceInfo]:
        async with self._lock:
            return self._devices.get(serial)

    async def list_all(self) -> list[DeviceInfo]:
        async with self._lock:
            return list(self._devices.values())

    async def list_online(self) -> list[DeviceInfo]:
        async with self._lock:
            return [d for d in self._devices.values() if d.state == DeviceState.DEVICE]

    def _is_emulator(self, serial: str) -> bool:
        return serial.startswith("emulator-")

    async def _fetch_device_details(self, serial: str) -> None:
        try:
            model_task = self._adb_getprop(serial, "ro.product.model")
            manufacturer_task = self._adb_getprop(serial, "ro.product.manufacturer")

            model, manufacturer = await asyncio.gather(model_task, manufacturer_task, return_exceptions=True)

            async with self._lock:
                if serial in self._devices:
                    device = self._devices[serial]
                    if isinstance(model, str):
                        device.model = model
                    if isinstance(manufacturer, str):
                        device.manufacturer = manufacturer
                    logger.info(f"Fetched details for {serial}: {manufacturer} {model}")

        except Exception as e:
            logger.error(f"Failed to fetch device details for {serial}: {e}")

    async def _adb_getprop(self, serial: str, prop: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "adb",
            "-s",
            serial,
            "shell",
            "getprop",
            prop,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip()
