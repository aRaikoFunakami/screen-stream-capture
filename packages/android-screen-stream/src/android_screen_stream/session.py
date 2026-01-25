"""
StreamSession - マルチキャスト対応のストリーミングセッション管理

複数クライアントへの同時配信、設定の動的変更をサポート
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

from .config import StreamConfig
from .client import ScrcpyClient

logger = logging.getLogger(__name__)


@dataclass
class StreamStats:
    """ストリーム統計情報"""
    bytes_sent: int = 0
    chunks_sent: int = 0
    subscriber_count: int = 0


class StreamSession:
    """デバイスごとのストリーミングセッション
    
    scrcpy-serverに接続し、raw H.264データを複数クライアントにブロードキャスト
    
    Examples:
        session = StreamSession("emulator-5554", server_jar="path/to/jar")
        await session.start()
        
        # 購読
        async for chunk in session.subscribe():
            await websocket.send_bytes(chunk)
        
        # 設定変更（セッション再起動）
        await session.update_config(StreamConfig.high_quality())
        
        # 停止
        await session.stop()
    """
    
    def __init__(
        self,
        serial: str,
        server_jar: str,
        config: Optional[StreamConfig] = None,
    ):
        """
        Args:
            serial: Android デバイスのシリアル番号
            server_jar: ローカルの scrcpy-server.jar ファイルパス
            config: ストリーミング設定 (省略時はデフォルト)
        """
        self.serial = serial
        self.server_jar = server_jar
        self.config = config or StreamConfig()
        
        self._client: Optional[ScrcpyClient] = None
        self._running = False
        self._subscribers: list[asyncio.Queue[bytes]] = []
        self._lock = asyncio.Lock()
        self._broadcast_task: Optional[asyncio.Task] = None
        self._stats = StreamStats()
    
    async def start(self) -> None:
        """ストリーミングセッションを開始"""
        if self._running:
            return
        
        logger.info(f"Starting stream session for {self.serial}")
        
        self._client = ScrcpyClient(
            serial=self.serial,
            server_jar=self.server_jar,
            config=self.config,
        )
        await self._client.start()
        
        self._running = True
        self._broadcast_task = asyncio.create_task(self._run_broadcast())
        
        logger.info(f"Stream session started for {self.serial}")
    
    async def stop(self) -> None:
        """ストリーミングセッションを停止"""
        if not self._running:
            return
        
        logger.info(f"Stopping stream session for {self.serial}")
        self._running = False
        
        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
        
        if self._client:
            await self._client.stop()
            self._client = None
        
        # 購読者に終了を通知
        async with self._lock:
            for queue in self._subscribers:
                try:
                    queue.put_nowait(b"")
                except asyncio.QueueFull:
                    pass
            self._subscribers.clear()
        
        logger.info(f"Stream session stopped for {self.serial}")
    
    async def update_config(self, config: StreamConfig) -> None:
        """設定を更新してセッションを再起動
        
        Args:
            config: 新しいストリーミング設定
        """
        logger.info(f"Updating config for {self.serial}: {config}")
        self.config = config
        
        if self._running:
            await self.stop()
            await self.start()
    
    async def subscribe(self) -> AsyncIterator[bytes]:
        """ストリームを購読
        
        Yields:
            bytes: H.264 データチャンク
        """
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
        
        async with self._lock:
            self._subscribers.append(queue)
            self._stats.subscriber_count = len(self._subscribers)
        
        logger.info(f"New subscriber for {self.serial}. Total: {len(self._subscribers)}")
        
        try:
            while self._running:
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=30.0)
                    if not chunk:  # 終了シグナル
                        break
                    yield chunk
                except asyncio.TimeoutError:
                    continue
        finally:
            async with self._lock:
                if queue in self._subscribers:
                    self._subscribers.remove(queue)
                self._stats.subscriber_count = len(self._subscribers)
            logger.info(f"Subscriber removed for {self.serial}. Total: {len(self._subscribers)}")
            
            # 購読者がいなくなったら遅延停止
            if not self._subscribers:
                asyncio.create_task(self._delayed_stop())
    
    async def _delayed_stop(self) -> None:
        """遅延停止（再接続の猶予）"""
        await asyncio.sleep(5.0)
        async with self._lock:
            if not self._subscribers:
                await self.stop()
    
    async def _run_broadcast(self) -> None:
        """データを全購読者にブロードキャスト"""
        if not self._client:
            return
        
        try:
            async for chunk in self._client.stream():
                if not self._running:
                    break
                
                self._stats.bytes_sent += len(chunk)
                self._stats.chunks_sent += 1
                
                async with self._lock:
                    for queue in self._subscribers:
                        try:
                            queue.put_nowait(chunk)
                        except asyncio.QueueFull:
                            pass  # クライアントが遅い場合はスキップ
        except Exception as e:
            logger.error(f"Broadcast error for {self.serial}: {e}")
        finally:
            self._running = False
    
    @property
    def is_running(self) -> bool:
        """セッションが起動中かどうか"""
        return self._running
    
    @property
    def subscriber_count(self) -> int:
        """現在の購読者数"""
        return len(self._subscribers)
    
    @property
    def stats(self) -> StreamStats:
        """ストリーム統計情報"""
        return self._stats


class StreamManager:
    """全デバイスのストリームセッションを管理
    
    Examples:
        manager = StreamManager(server_jar="path/to/jar")
        
        # セッション取得または作成
        session = await manager.get_or_create("emulator-5554")
        
        # 購読
        async for chunk in session.subscribe():
            await websocket.send_bytes(chunk)
        
        # 全停止
        await manager.stop_all()
    """
    
    def __init__(
        self,
        server_jar: str,
        default_config: Optional[StreamConfig] = None,
    ):
        """
        Args:
            server_jar: ローカルの scrcpy-server.jar ファイルパス
            default_config: デフォルトのストリーミング設定
        """
        self.server_jar = server_jar
        self.default_config = default_config or StreamConfig()
        self._sessions: dict[str, StreamSession] = {}
        self._lock = asyncio.Lock()
    
    async def get_or_create(
        self,
        serial: str,
        config: Optional[StreamConfig] = None,
    ) -> StreamSession:
        """セッションを取得または作成
        
        Args:
            serial: Android デバイスのシリアル番号
            config: ストリーミング設定 (省略時はデフォルト)
        
        Returns:
            StreamSession: ストリームセッション
        """
        async with self._lock:
            if serial in self._sessions:
                session = self._sessions[serial]
                if session.is_running:
                    return session
                # 停止していたら削除して再作成
                try:
                    await session.stop()
                except Exception:
                    pass
                del self._sessions[serial]
            
            session = StreamSession(
                serial=serial,
                server_jar=self.server_jar,
                config=config or self.default_config,
            )
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
    
    def get_session(self, serial: str) -> Optional[StreamSession]:
        """セッションを取得 (存在しない場合は None)"""
        return self._sessions.get(serial)
    
    @property
    def active_sessions(self) -> list[str]:
        """アクティブなセッションのシリアル番号リスト"""
        return [s for s, session in self._sessions.items() if session.is_running]
