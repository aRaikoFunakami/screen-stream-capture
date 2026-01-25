"""Screen Stream Capture Backend - FastAPI Application"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Screen Stream Capture",
    description="Android デバイス画面ストリーミング & キャプチャシステム",
    version="0.1.0",
)

# CORS 設定（開発用：全許可）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz() -> dict:
    """ヘルスチェックエンドポイント"""
    return {
        "status": "ok",
        "version": "0.1.0",
    }


@app.get("/api/devices")
async def get_devices() -> list:
    """デバイス一覧を取得（仮実装）"""
    return []

