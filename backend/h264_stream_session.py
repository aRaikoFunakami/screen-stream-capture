"""
H.264ストリームセッション管理 - scrcpy-server直接接続
WebSocket経由でraw H.264データをブラウザに送信
"""

import asyncio
import logging
from typing import AsyncIterator, Optional
from dataclasses import dataclass

from scrcpy_client import ScrcpyRawClient, ScrcpyConfig

logger = logging.getLogger(__name__)


@dataclass
class StreamStats:
    """ストリーム統計"""
    bytes_sent: int = 0
    chunks_sent: int = 0
    subscriber_count: int = 0


class H264StreamSession:
    """デバイスごとのH.264ストリーミングセッション
    
    scrcpy-serverに直接接続し、raw H.264データを複数クライアントにブロードキャスト
    """
    
    def __init__(self, serial: str, config: Optional[ScrcpyConfig] = None):
        self.serial = serial
        self.config = config or ScrcpyConfig(max_size=720, max_fps=30)
        
        self._client: Optional[ScrcpyRawClient] = None
        self._running = False
        self._subscribers: list[asyncio.Queue[bytes]] = []
        self._lock = asyncio.Lock()
        self._broadcast_task: Optional[asyncio.Task] = None
        self._stats = StreamStats()
    
    async def start(self) -> None:
        """ストリーミングセッションを開始"""
        if self._running:
            return
        
        logger.info(f"Starting H.264 stream session for {self.serial}")
        
        # scrcpyクライアントを起動
        self._client = ScrcpyRawClient(
            device_serial=self.serial,
            config=self.config,
        )
        await self._client.start()
        
        self._running = True
        
        # ブロードキャストタスクを開始
        self._broadcast_task = asyncio.create_task(self._run_broadcast())
        
        logger.info(f"H.264 stream session started for {self.serial}")
    
    async def stop(self) -> None:
        """ストリーミングセッションを停止"""
        if not self._running:
            return
        
        logger.info(f"Stopping H.264 stream session for {self.serial}")
        self._running = False
        
        # タスクをキャンセル
        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
        
        # クライアントを停止
        if self._client:
            await self._client.stop()
            self._client = None
        
        # 購読者に終了を通知
        async with self._lock:
            for queue in self._subscribers:
                try:
                    queue.put_nowait(b"")  # 空バイトで終了シグナル
                except asyncio.QueueFull:
                    pass
            self._subscribers.clear()
        
        logger.info(f"H.264 stream session stopped for {self.serial}")
    
    async def subscribe(self) -> AsyncIterator[bytes]:
        """ストリームを購読"""
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
        
        async with self._lock:
            self._subscribers.append(queue)
            self._stats.subscriber_count = len(self._subscribers)
        
        logger.info(f"New H.264 subscriber for {self.serial}. Total: {len(self._subscribers)}")
        
        try:
            while self._running:
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=30.0)
                    if not chunk:  # 終了シグナル
                        break
                    yield chunk
                except asyncio.TimeoutError:
                    # タイムアウト時は継続
                    continue
        finally:
            async with self._lock:
                if queue in self._subscribers:
                    self._subscribers.remove(queue)
                self._stats.subscriber_count = len(self._subscribers)
            logger.info(f"H.264 subscriber removed for {self.serial}. Total: {len(self._subscribers)}")
            
            # 購読者がいなくなったらセッション停止
            if not self._subscribers:
                asyncio.create_task(self._delayed_stop())
    
    async def _delayed_stop(self) -> None:
        """遅延停止（再接続の猶予）"""
        await asyncio.sleep(5.0)
        async with self._lock:
            if not self._subscribers:
                await self.stop()
    
    async def _run_broadcast(self) -> None:
        """H.264データを全購読者にブロードキャスト"""
        if not self._client:
            return
        
        try:
            async for chunk in self._client.stream():
                if not self._running:
                    break
                
                self._stats.bytes_sent += len(chunk)
                self._stats.chunks_sent += 1
                
                async with self._lock:
                    dead_queues = []
                    for queue in self._subscribers:
                        try:
                            queue.put_nowait(chunk)
                        except asyncio.QueueFull:
                            # キューがフルの場合はスキップ（クライアントが遅い）
                            pass
                    
                    for queue in dead_queues:
                        self._subscribers.remove(queue)
        except Exception as e:
            logger.error(f"Broadcast error for {self.serial}: {e}")
        finally:
            self._running = False
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
    
    @property
    def stats(self) -> StreamStats:
        return self._stats


class H264StreamManager:
    """全デバイスのH.264ストリームセッションを管理"""
    
    def __init__(self):
        self._sessions: dict[str, H264StreamSession] = {}
        self._lock = asyncio.Lock()
    
    async def get_or_create(self, serial: str) -> H264StreamSession:
        """セッションを取得または作成"""
        async with self._lock:
            # 既存セッションがあるか確認
            if serial in self._sessions:
                session = self._sessions[serial]
                # セッションが停止していたら削除して再作成
                if not session.is_running:
                    logger.info(f"Session for {serial} is not running, recreating")
                    try:
                        await session.stop()
                    except Exception:
                        pass
                    del self._sessions[serial]
                else:
                    return session
            
            # 新規セッション作成
            session = H264StreamSession(serial)
            await session.start()
            self._sessions[serial] = session
            return session
    
    async def stop_session(self, serial: str) -> None:
        """セッションを停止"""
        async with self._lock:
            if serial in self._sessions:
                session = self._sessions.pop(serial)
                await session.stop()
    
    async def stop_all(self) -> None:
        """全セッションを停止"""
        async with self._lock:
            for session in self._sessions.values():
                await session.stop()
            self._sessions.clear()
    
    def get_session(self, serial: str) -> Optional[H264StreamSession]:
        """セッションを取得"""
        return self._sessions.get(serial)


# シングルトンインスタンス
_h264_stream_manager: Optional[H264StreamManager] = None


def get_h264_stream_manager() -> H264StreamManager:
    """H264StreamManagerのシングルトンインスタンスを取得"""
    global _h264_stream_manager
    if _h264_stream_manager is None:
        _h264_stream_manager = H264StreamManager()
    return _h264_stream_manager
