"""ADB デバイスモニター - track-devices によるイベント駆動監視"""

import asyncio
import logging
from typing import Callable, Optional

from models import DeviceState

logger = logging.getLogger(__name__)


class DeviceMonitor:
    """adb track-devices を購読し、デバイス変更イベントを発行
    
    ポーリングを使用せず、ADB のイベントストリームを監視する。
    """
    
    def __init__(self):
        self._process: Optional[asyncio.subprocess.Process] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # コールバック
        self._on_connected: list[Callable[[str, DeviceState], None]] = []
        self._on_disconnected: list[Callable[[str], None]] = []
        self._on_state_changed: list[Callable[[str, DeviceState], None]] = []
        
        # 現在のデバイス状態（差分検出用）
        self._current_devices: dict[str, DeviceState] = {}
    
    def on_device_connected(self, callback: Callable[[str, DeviceState], None]) -> None:
        """デバイス接続時のコールバックを登録"""
        self._on_connected.append(callback)
    
    def on_device_disconnected(self, callback: Callable[[str], None]) -> None:
        """デバイス切断時のコールバックを登録"""
        self._on_disconnected.append(callback)
    
    def on_state_changed(self, callback: Callable[[str, DeviceState], None]) -> None:
        """デバイス状態変更時のコールバックを登録"""
        self._on_state_changed.append(callback)
    
    async def start(self) -> None:
        """監視を開始"""
        if self._running:
            logger.warning("DeviceMonitor is already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("DeviceMonitor started")
    
    async def stop(self) -> None:
        """監視を停止"""
        self._running = False
        
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
            except ProcessLookupError:
                # プロセスが既に終了している
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
        """監視ループ - track-devices の出力を読み取り続ける"""
        while self._running:
            try:
                await self._run_track_devices()
            except Exception as e:
                logger.error(f"Error in track-devices: {e}")
                if self._running:
                    # 再接続を試みる
                    await asyncio.sleep(2.0)
    
    async def _run_track_devices(self) -> None:
        """adb track-devices を実行し、出力をパース"""
        self._process = await asyncio.create_subprocess_exec(
            "adb", "track-devices",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        logger.info("Started adb track-devices")
        
        try:
            while self._running and self._process.stdout:
                # 4バイトの長さプレフィックスを読み取り
                length_hex = await self._process.stdout.read(4)
                if not length_hex:
                    break
                
                try:
                    length = int(length_hex.decode(), 16)
                except ValueError:
                    logger.error(f"Invalid length prefix: {length_hex}")
                    continue
                
                if length == 0:
                    # 空のデバイスリスト
                    await self._process_device_list("")
                    continue
                
                # デバイスリストを読み取り
                data = await self._process.stdout.read(length)
                if not data:
                    break
                
                await self._process_device_list(data.decode().strip())
                
        finally:
            if self._process:
                self._process.terminate()
                await self._process.wait()
    
    async def _process_device_list(self, data: str) -> None:
        """デバイスリストをパースし、変更をコールバックで通知"""
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
        
        # 差分を検出
        old_serials = set(self._current_devices.keys())
        new_serials = set(new_devices.keys())
        
        # 新規接続
        for serial in new_serials - old_serials:
            state = new_devices[serial]
            logger.info(f"Device connected: {serial} ({state.value})")
            for callback in self._on_connected:
                try:
                    callback(serial, state)
                except Exception as e:
                    logger.error(f"Error in on_connected callback: {e}")
        
        # 切断
        for serial in old_serials - new_serials:
            logger.info(f"Device disconnected: {serial}")
            for callback in self._on_disconnected:
                try:
                    callback(serial)
                except Exception as e:
                    logger.error(f"Error in on_disconnected callback: {e}")
        
        # 状態変更
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
        """状態文字列をパース"""
        state_map = {
            "device": DeviceState.DEVICE,
            "offline": DeviceState.OFFLINE,
            "unauthorized": DeviceState.UNAUTHORIZED,
            "connecting": DeviceState.CONNECTING,
        }
        return state_map.get(state_str.lower(), DeviceState.UNKNOWN)
    
    def get_current_devices(self) -> dict[str, DeviceState]:
        """現在のデバイス一覧を取得"""
        return self._current_devices.copy()
