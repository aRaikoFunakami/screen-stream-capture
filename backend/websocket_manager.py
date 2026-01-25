"""WebSocket 接続管理 - リアルタイム通知"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 接続を管理"""
    
    def __init__(self):
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket) -> None:
        """新しい接続を追加"""
        await websocket.accept()
        async with self._lock:
            self._connections.append(websocket)
        logger.info(f"WebSocket connected. Total: {len(self._connections)}")
    
    async def disconnect(self, websocket: WebSocket) -> None:
        """接続を削除"""
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self._connections)}")
    
    async def broadcast(self, message: dict) -> None:
        """全接続にメッセージをブロードキャスト"""
        async with self._lock:
            connections = self._connections.copy()
        
        if not connections:
            return
        
        data = json.dumps(message)
        dead_connections = []
        
        for websocket in connections:
            try:
                await websocket.send_text(data)
            except Exception as e:
                logger.warning(f"Failed to send to websocket: {e}")
                dead_connections.append(websocket)
        
        # 切断された接続を削除
        if dead_connections:
            async with self._lock:
                for ws in dead_connections:
                    if ws in self._connections:
                        self._connections.remove(ws)
    
    async def send_to(self, websocket: WebSocket, message: dict) -> bool:
        """特定の接続にメッセージを送信"""
        try:
            await websocket.send_text(json.dumps(message))
            return True
        except Exception as e:
            logger.warning(f"Failed to send to websocket: {e}")
            return False


# シングルトンインスタンス
_connection_manager: Optional[ConnectionManager] = None


def get_connection_manager() -> ConnectionManager:
    """ConnectionManager のシングルトンインスタンスを取得"""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
    return _connection_manager
