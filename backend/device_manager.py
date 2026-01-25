"""デバイス管理サービス - Monitor と Registry の統合"""

import asyncio
import logging
from typing import Callable, Optional

from device_monitor import DeviceMonitor
from device_registry import DeviceRegistry
from models import DeviceInfo, DeviceState

logger = logging.getLogger(__name__)


class DeviceManager:
    """デバイス管理の統合サービス
    
    DeviceMonitor と DeviceRegistry を連携させ、
    デバイスイベントの監視と情報管理を一元化する。
    """
    
    def __init__(self):
        self.monitor = DeviceMonitor()
        self.registry = DeviceRegistry()
        
        # 外部通知用コールバック（WebSocket 等で使用）
        self._change_callbacks: list[Callable[[], None]] = []
        
        # Monitor のコールバックを設定
        self.monitor.on_device_connected(self._handle_connected)
        self.monitor.on_device_disconnected(self._handle_disconnected)
        self.monitor.on_state_changed(self._handle_state_changed)
    
    def on_change(self, callback: Callable[[], None]) -> None:
        """デバイス一覧に変更があった時のコールバックを登録"""
        self._change_callbacks.append(callback)
    
    async def start(self) -> None:
        """監視を開始"""
        await self.monitor.start()
        logger.info("DeviceManager started")
    
    async def stop(self) -> None:
        """監視を停止"""
        await self.monitor.stop()
        logger.info("DeviceManager stopped")
    
    async def get_device(self, serial: str) -> Optional[DeviceInfo]:
        """デバイス情報を取得"""
        return await self.registry.get(serial)
    
    async def list_devices(self) -> list[DeviceInfo]:
        """全デバイス一覧を取得"""
        return await self.registry.list_all()
    
    async def list_online_devices(self) -> list[DeviceInfo]:
        """オンラインデバイス一覧を取得"""
        return await self.registry.list_online()
    
    def _handle_connected(self, serial: str, state: DeviceState) -> None:
        """デバイス接続時の処理"""
        asyncio.create_task(self._async_handle_connected(serial, state))
    
    async def _async_handle_connected(self, serial: str, state: DeviceState) -> None:
        """デバイス接続時の非同期処理"""
        await self.registry.register(serial, state)
        self._notify_change()
    
    def _handle_disconnected(self, serial: str) -> None:
        """デバイス切断時の処理"""
        asyncio.create_task(self._async_handle_disconnected(serial))
    
    async def _async_handle_disconnected(self, serial: str) -> None:
        """デバイス切断時の非同期処理"""
        await self.registry.unregister(serial)
        self._notify_change()
    
    def _handle_state_changed(self, serial: str, state: DeviceState) -> None:
        """状態変更時の処理"""
        asyncio.create_task(self._async_handle_state_changed(serial, state))
    
    async def _async_handle_state_changed(self, serial: str, state: DeviceState) -> None:
        """状態変更時の非同期処理"""
        await self.registry.update_state(serial, state)
        self._notify_change()
    
    def _notify_change(self) -> None:
        """変更通知を発行"""
        for callback in self._change_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in change callback: {e}")


# シングルトンインスタンス
_device_manager: Optional[DeviceManager] = None


def get_device_manager() -> DeviceManager:
    """DeviceManager のシングルトンインスタンスを取得"""
    global _device_manager
    if _device_manager is None:
        _device_manager = DeviceManager()
    return _device_manager
