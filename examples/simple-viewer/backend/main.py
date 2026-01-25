"""
Simple Android Screen Viewer - Backend

最小構成の Android 画面ストリーミングバックエンド
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from android_screen_stream import StreamManager, StreamConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# scrcpy-server.jar のパス（環境変数または相対パス）
SCRCPY_SERVER_JAR = os.environ.get(
    "SCRCPY_SERVER_JAR",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "vendor", "scrcpy-server.jar")
)

# StreamManager インスタンス
stream_manager: StreamManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションのライフサイクル管理"""
    global stream_manager
    
    logger.info(f"Using scrcpy-server.jar: {SCRCPY_SERVER_JAR}")
    
    stream_manager = StreamManager(
        server_jar=SCRCPY_SERVER_JAR,
        default_config=StreamConfig.balanced(),
    )
    
    yield
    
    # シャットダウン時に全セッション停止
    if stream_manager:
        await stream_manager.stop_all()


app = FastAPI(
    title="Simple Android Screen Viewer",
    lifespan=lifespan,
)

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz():
    """ヘルスチェック"""
    return {"status": "ok"}


@app.get("/api/sessions")
async def list_sessions():
    """アクティブなセッション一覧"""
    if not stream_manager:
        return {"sessions": []}
    return {"sessions": stream_manager.active_sessions}


@app.websocket("/api/ws/stream/{serial}")
async def websocket_stream(websocket: WebSocket, serial: str):
    """H.264 ストリーミング WebSocket エンドポイント"""
    await websocket.accept()
    
    if not stream_manager:
        await websocket.close(code=1011, reason="Server not ready")
        return
    
    logger.info(f"WebSocket connected for device: {serial}")
    
    try:
        # セッションを取得または作成
        session = await stream_manager.get_or_create(serial)
        
        # ストリームを購読
        async for chunk in session.subscribe():
            await websocket.send_bytes(chunk)
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for device: {serial}")
    except Exception as e:
        logger.error(f"WebSocket error for device {serial}: {e}")
        await websocket.close(code=1011, reason=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
