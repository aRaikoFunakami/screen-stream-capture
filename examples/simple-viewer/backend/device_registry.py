"""デバイスレジストリ - デバイス情報のキャッシュと管理"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from models import DeviceInfo, DeviceState

logger = logging.getLogger(__name__)


class DeviceRegistry:
    """デバイス情報を管理するレジストリ
    
    DeviceMonitor からのイベントを受け取り、デバイス情報を保持する。
    adb shell コマンドで詳細情報を取得してキャッシュする。
    """
    
    def __init__(self):
        self._devices: dict[str, DeviceInfo] = {}
        self._lock = asyncio.Lock()
    
    async def register(self, serial: str, state: DeviceState) -> DeviceInfo:
        """デバイスを登録（または更新）"""
        async with self._lock:
            if serial in self._devices:
                # 既存デバイスの状態更新
                device = self._devices[serial]
                device.state = state
                device.last_seen = datetime.now()
            else:
                # 新規デバイス登録
                device = DeviceInfo(
                    serial=serial,
                    state=state,
                    is_emulator=self._is_emulator(serial),
                )
                self._devices[serial] = device
                
                # 詳細情報を非同期で取得
                if state == DeviceState.DEVICE:
                    asyncio.create_task(self._fetch_device_details(serial))
            
            return device
    
    async def unregister(self, serial: str) -> Optional[DeviceInfo]:
        """デバイスを登録解除"""
        async with self._lock:
            return self._devices.pop(serial, None)
    
    async def update_state(self, serial: str, state: DeviceState) -> Optional[DeviceInfo]:
        """デバイス状態を更新"""
        async with self._lock:
            if serial in self._devices:
                device = self._devices[serial]
                device.state = state
                device.last_seen = datetime.now()
                
                # device 状態になったら詳細情報を取得
                if state == DeviceState.DEVICE and not device.model:
                    asyncio.create_task(self._fetch_device_details(serial))
                
                return device
            return None
    
    async def get(self, serial: str) -> Optional[DeviceInfo]:
        """デバイス情報を取得"""
        async with self._lock:
            return self._devices.get(serial)
    
    async def list_all(self) -> list[DeviceInfo]:
        """全デバイス情報を取得"""
        async with self._lock:
            return list(self._devices.values())
    
    async def list_online(self) -> list[DeviceInfo]:
        """オンラインデバイスのみ取得"""
        async with self._lock:
            return [d for d in self._devices.values() if d.state == DeviceState.DEVICE]
    
    def _is_emulator(self, serial: str) -> bool:
        """エミュレータ判定"""
        # エミュレータは通常 "emulator-5554" のような形式
        return serial.startswith("emulator-")
    
    async def _fetch_device_details(self, serial: str) -> None:
        """デバイスの詳細情報を adb shell で取得"""
        try:
            # 並列で情報取得
            model_task = self._adb_getprop(serial, "ro.product.model")
            manufacturer_task = self._adb_getprop(serial, "ro.product.manufacturer")
            
            model, manufacturer = await asyncio.gather(
                model_task, manufacturer_task, return_exceptions=True
            )
            
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
        """adb shell getprop を実行"""
        proc = await asyncio.create_subprocess_exec(
            "adb", "-s", serial, "shell", "getprop", prop,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip()
