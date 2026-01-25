"""ストリームセッション管理 - scrcpy(file) + tail -f + ffmpeg パイプライン"""

import asyncio
import logging
from typing import AsyncGenerator, Optional

from scrcpy_process import ScrcpyRecorder
from fmp4_muxer import Fmp4Muxer

logger = logging.getLogger(__name__)


class StreamSession:
    """デバイスごとのストリーミングセッション

    scrcpy → file(mkv) → tail -f → ffmpeg → fMP4 パイプラインを管理し、
    複数クライアントへのマルチキャストを実現する。
    """

    def __init__(self, serial: str):
        self.serial = serial
        self._recorder = ScrcpyRecorder(serial)
        self._muxer: Optional[Fmp4Muxer] = None

        self._running = False
        self._subscribers: list[asyncio.Queue[bytes]] = []
        self._lock = asyncio.Lock()

        self._broadcast_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """ストリーミングセッションを開始"""
        if self._running:
            return

        logger.info(f"Starting stream session for {self.serial}")

        # scrcpy を起動（ファイルに書き込み開始）
        await self._recorder.start()

        # tail -f + ffmpeg を起動（ファイルが存在するまで内部で待機）
        self._muxer = Fmp4Muxer(self._recorder.record_path)
        await self._muxer.start()

        self._running = True

        # ブロードキャストタスクを開始
        self._broadcast_task = asyncio.create_task(self._run_broadcast())

        logger.info(f"Stream session started for {self.serial}")

    async def stop(self) -> None:
        """ストリーミングセッションを停止"""
        if not self._running:
            return

        logger.info(f"Stopping stream session for {self.serial}")
        self._running = False

        # タスクをキャンセル
        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass

        # プロセスを停止（順序重要: muxer → scrcpy）
        if self._muxer:
            await self._muxer.stop()
        await self._recorder.stop()

        # 購読者に終了を通知
        async with self._lock:
            for queue in self._subscribers:
                try:
                    queue.put_nowait(b"")  # 空バイトで終了シグナル
                except asyncio.QueueFull:
                    pass
            self._subscribers.clear()

        logger.info(f"Stream session stopped for {self.serial}")

    async def subscribe(self) -> AsyncGenerator[bytes, None]:
        """ストリームを購読"""
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)

        async with self._lock:
            self._subscribers.append(queue)

        logger.info(f"New subscriber for {self.serial}. Total: {len(self._subscribers)}")

        try:
            while self._running:
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=30.0)
                    if not chunk:  # 終了シグナル
                        break
                    yield chunk
                except asyncio.TimeoutError:
                    # タイムアウト時は継続（keepalive）
                    continue
        finally:
            async with self._lock:
                if queue in self._subscribers:
                    self._subscribers.remove(queue)
            logger.info(f"Subscriber removed for {self.serial}. Total: {len(self._subscribers)}")

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
        """ffmpeg 出力を全購読者にブロードキャスト"""
        if not self._muxer:
            return

        try:
            async for chunk in self._muxer.read_stream():
                if not self._running:
                    break

                async with self._lock:
                    dead_queues = []
                    for queue in self._subscribers:
                        try:
                            queue.put_nowait(chunk)
                        except asyncio.QueueFull:
                            dead_queues.append(queue)

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


class StreamManager:
    """全デバイスのストリームセッションを管理"""
    
    def __init__(self):
        self._sessions: dict[str, StreamSession] = {}
        self._lock = asyncio.Lock()
    
    async def get_or_create(self, serial: str) -> StreamSession:
        """セッションを取得または作成"""
        async with self._lock:
            if serial not in self._sessions:
                session = StreamSession(serial)
                await session.start()
                self._sessions[serial] = session
            return self._sessions[serial]
    
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
        """セッションを取得"""
        return self._sessions.get(serial)


# シングルトンインスタンス
_stream_manager: Optional[StreamManager] = None


def get_stream_manager() -> StreamManager:
    """StreamManager のシングルトンインスタンスを取得"""
    global _stream_manager
    if _stream_manager is None:
        _stream_manager = StreamManager()
    return _stream_manager
