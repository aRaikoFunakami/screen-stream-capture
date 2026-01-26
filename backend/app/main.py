"""Screen Stream Capture Backend - FastAPI Application

FastAPI の推奨される構成（app/api/core/services）に沿って実装する公式バックエンド。

- デバイス管理 (DeviceManager / adb track-devices)
- SSE によるデバイス変更通知 (/api/events)
- H.264 WebSocket ストリーミング (/api/ws/stream/{serial})

API ドキュメントは FastAPI の OpenAPI 生成を活用し、`/docs` で確認できる。
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from android_screen_stream import StreamConfig, StreamManager

from app.api.router import api_router
from app.api.endpoints import healthz
from app.core.config import load_settings
from app.core.logging import configure_logging
from app.services.capture_manager import get_capture_manager
from app.services.device_manager import get_device_manager
from app.services.sse_manager import get_sse_manager

logger = logging.getLogger(__name__)


def _setup_device_change_notifier(app: FastAPI) -> None:
    """デバイス変更時に SSE で通知する設定"""

    device_manager = get_device_manager()
    sse_manager = get_sse_manager()

    def on_device_change() -> None:
        asyncio.create_task(notify_device_change())

    async def notify_device_change() -> None:
        devices = await device_manager.list_devices()
        await sse_manager.broadcast("devices", [d.to_dict() for d in devices])

    device_manager.on_change(on_device_change)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    app.state.settings = settings

    logger.info("Starting services...")
    logger.info(f"Using scrcpy-server.jar: {settings.scrcpy_server_jar}")

    device_manager = get_device_manager()
    _setup_device_change_notifier(app)
    await device_manager.start()

    app.state.stream_manager = StreamManager(
        server_jar=settings.scrcpy_server_jar,
        default_config=StreamConfig.balanced(),
    )

    app.state.capture_manager = get_capture_manager(
        stream_manager=app.state.stream_manager,
        output_dir=settings.capture_output_dir,
    )

    yield

    logger.info("Stopping services...")
    capture_manager = getattr(app.state, "capture_manager", None)
    if capture_manager:
        await capture_manager.stop_all()
    stream_manager = getattr(app.state, "stream_manager", None)
    if stream_manager:
        await stream_manager.stop_all()
    await device_manager.stop()


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="Screen Stream Capture",
        description="Android デバイス画面ストリーミング & キャプチャシステム",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=[
            {"name": "health", "description": "Health check"},
            {"name": "devices", "description": "Device discovery"},
            {"name": "events", "description": "SSE events"},
            {"name": "sessions", "description": "Stream session management"},
            {"name": "stream", "description": "WebSocket H.264 streaming"},
            {"name": "capture", "description": "WebSocket JPEG capture"},
        ],
    )

    settings = load_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # root level
    app.include_router(healthz.router, tags=["health"])

    # /api
    app.include_router(api_router)

    return app


app = create_app()
