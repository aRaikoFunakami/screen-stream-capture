"""SSE (Server-Sent Events) 管理"""

import asyncio
import json
import logging
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


class SSEManager:
    """SSE 接続を管理し、イベントをブロードキャスト"""
    
    def __init__(self):
        self._queues: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()
    
    async def subscribe(self) -> AsyncGenerator[str, None]:
        """SSE ストリームを購読"""
        queue: asyncio.Queue = asyncio.Queue()
        
        async with self._lock:
            self._queues.append(queue)
        logger.info(f"SSE client connected. Total: {len(self._queues)}")
        
        try:
            while True:
                data = await queue.get()
                yield data
        finally:
            async with self._lock:
                if queue in self._queues:
                    self._queues.remove(queue)
            logger.info(f"SSE client disconnected. Total: {len(self._queues)}")
    
    async def broadcast(self, event: str, data: dict) -> None:
        """全クライアントにイベントを送信"""
        message = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        
        async with self._lock:
            queues = self._queues.copy()
        
        for queue in queues:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("SSE queue full, dropping message")


# シングルトンインスタンス
_sse_manager: SSEManager | None = None


def get_sse_manager() -> SSEManager:
    """SSEManager のシングルトンインスタンスを取得"""
    global _sse_manager
    if _sse_manager is None:
        _sse_manager = SSEManager()
    return _sse_manager
