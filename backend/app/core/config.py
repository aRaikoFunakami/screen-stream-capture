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


def load_settings() -> Settings:
    """環境変数から Settings を生成する。"""

    scrcpy_server_jar = os.environ.get("SCRCPY_SERVER_JAR", "/app/vendor/scrcpy-server.jar")

    cors = os.environ.get("CORS_ALLOW_ORIGINS", "*")
    cors_allow_origins = [o.strip() for o in cors.split(",") if o.strip()]

    return Settings(
        scrcpy_server_jar=scrcpy_server_jar,
        cors_allow_origins=cors_allow_origins,
    )
