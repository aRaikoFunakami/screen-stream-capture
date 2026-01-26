"""Runtime configuration for the FastAPI backend.

FastAPI の "王道" 構成として core 配下に設定読み込みを集約する。
依存を増やさないため pydantic-settings は使わず、環境変数から読む。
"""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    """バックエンド設定"""

    scrcpy_server_jar: str
    cors_allow_origins: list[str]
    capture_output_dir: str
    capture_jpeg_quality: int
    stream_idle_timeout_sec: float


def load_settings() -> Settings:
    """環境変数から Settings を生成する。"""

    scrcpy_server_jar = os.environ.get("SCRCPY_SERVER_JAR", "/app/vendor/scrcpy-server.jar")

    cors = os.environ.get("CORS_ALLOW_ORIGINS", "*")
    cors_allow_origins = [o.strip() for o in cors.split(",") if o.strip()]

    # In docker-compose, backend is mounted to /app/backend (rw), and the process
    # runs with WORKDIR=/app/backend. Defaulting to a relative path makes captures
    # persist on the host without extra volume config.
    capture_output_dir = os.environ.get("CAPTURE_OUTPUT_DIR", "captures")

    capture_jpeg_quality = int(os.environ.get("CAPTURE_JPEG_QUALITY", "80"))
    if capture_jpeg_quality < 1:
        capture_jpeg_quality = 1
    if capture_jpeg_quality > 100:
        capture_jpeg_quality = 100

    stream_idle_timeout_sec = float(os.environ.get("STREAM_IDLE_TIMEOUT_SEC", "5"))

    return Settings(
        scrcpy_server_jar=scrcpy_server_jar,
        cors_allow_origins=cors_allow_origins,
        capture_output_dir=capture_output_dir,
        capture_jpeg_quality=capture_jpeg_quality,
        stream_idle_timeout_sec=stream_idle_timeout_sec,
    )
