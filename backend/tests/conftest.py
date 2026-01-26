"""総合テスト用 conftest.py

このファイルは実際の実装を使った総合テストのための pytest fixtures を提供します。
モックは使用せず、実際のデバイス・scrcpy・ffmpeg を使用します。

前提条件:
- adb がインストールされていること
- adb devices で少なくとも1台のデバイスが接続されていること
- scrcpy-server.jar が vendor/ に存在すること（SCRCPY_SERVER_JAR 環境変数で指定可能）
- ffmpeg がインストールされていること
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest


# =============================================================================
# テスト環境チェック
# =============================================================================

@dataclass
class EnvironmentCheckResult:
    """環境チェックの結果"""
    passed: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: dict[str, str] = field(default_factory=dict)

    def add_error(self, message: str) -> None:
        self.passed = False
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_info(self, key: str, value: str) -> None:
        self.info[key] = value


def check_command_available(command: str) -> tuple[bool, str | None]:
    """コマンドが利用可能かチェック"""
    path = shutil.which(command)
    if path:
        return True, path
    return False, None


def check_command_version(command: str, version_args: list[str] | None = None) -> str | None:
    """コマンドのバージョンを取得"""
    args = version_args or ["--version"]
    try:
        result = subprocess.run(
            [command] + args,
            capture_output=True,
            text=True,
            timeout=10,
        )
        # 最初の行だけ取得
        output = result.stdout.strip() or result.stderr.strip()
        return output.split("\n")[0] if output else None
    except Exception:
        return None


def check_adb_devices() -> tuple[list[str], str]:
    """adb devices の結果を取得"""
    try:
        result = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = result.stdout.strip().split("\n")[1:]
        devices = []
        for line in lines:
            if "\tdevice" in line:
                serial = line.split("\t")[0]
                devices.append(serial)
        return devices, result.stdout.strip()
    except FileNotFoundError:
        return [], "adb command not found"
    except subprocess.TimeoutExpired:
        return [], "adb command timed out"
    except Exception as e:
        return [], str(e)


def find_scrcpy_server_jar() -> Path | None:
    """scrcpy-server.jar のパスを探す"""
    # 環境変数で指定されている場合
    env_path = os.environ.get("SCRCPY_SERVER_JAR")
    if env_path:
        path = Path(env_path)
        if path.exists():
            return path

    # プロジェクトルートからの相対パス
    project_root = Path(__file__).parent.parent.parent
    candidates = [
        project_root / "vendor" / "scrcpy-server.jar",
        project_root / "scrcpy" / "scrcpy-server.jar",
        Path.home() / ".local" / "share" / "scrcpy" / "scrcpy-server.jar",
    ]
    
    for path in candidates:
        if path.exists():
            return path
    
    return None


def check_test_environment() -> EnvironmentCheckResult:
    """テスト環境をチェックし、結果を返す"""
    result = EnvironmentCheckResult()

    # 1. adb チェック
    adb_available, adb_path = check_command_available("adb")
    if not adb_available:
        result.add_error(
            "adb がインストールされていません。\n"
            "  修正方法:\n"
            "    macOS: brew install android-platform-tools\n"
            "    Ubuntu: sudo apt install adb\n"
            "    Windows: Android SDK をインストールして PATH に追加"
        )
    else:
        result.add_info("adb_path", adb_path or "unknown")
        adb_version = check_command_version("adb")
        if adb_version:
            result.add_info("adb_version", adb_version)

    # 2. adb デバイス接続チェック
    if adb_available:
        devices, adb_output = check_adb_devices()
        if not devices:
            result.add_error(
                "接続中の Android デバイスがありません。\n"
                "  修正方法:\n"
                "    1. Android デバイスを USB で接続する\n"
                "    2. デバイスで USB デバッグを有効にする\n"
                "    3. 'adb devices' で 'device' 状態になっていることを確認\n"
                "    4. エミュレータを使う場合: 'emulator -avd <name>' で起動\n"
                f"  現在の adb devices 出力:\n    {adb_output.replace(chr(10), chr(10) + '    ')}"
            )
        else:
            result.add_info("connected_devices", ", ".join(devices))
            result.add_info("device_count", str(len(devices)))

    # 3. ffmpeg チェック
    ffmpeg_available, ffmpeg_path = check_command_available("ffmpeg")
    if not ffmpeg_available:
        result.add_error(
            "ffmpeg がインストールされていません。\n"
            "  修正方法:\n"
            "    macOS: brew install ffmpeg\n"
            "    Ubuntu: sudo apt install ffmpeg\n"
            "    Windows: https://ffmpeg.org/download.html からダウンロード"
        )
    else:
        result.add_info("ffmpeg_path", ffmpeg_path or "unknown")
        ffmpeg_version = check_command_version("ffmpeg", ["-version"])
        if ffmpeg_version:
            result.add_info("ffmpeg_version", ffmpeg_version)

    # 4. scrcpy-server.jar チェック
    scrcpy_jar = find_scrcpy_server_jar()
    if not scrcpy_jar:
        result.add_error(
            "scrcpy-server.jar が見つかりません。\n"
            "  修正方法:\n"
            "    1. プロジェクトルートで 'make setup' を実行\n"
            "    2. または環境変数 SCRCPY_SERVER_JAR でパスを指定\n"
            "  探索したパス:\n"
            "    - vendor/scrcpy-server.jar\n"
            "    - scrcpy/scrcpy-server.jar\n"
            "    - ~/.local/share/scrcpy/scrcpy-server.jar"
        )
    else:
        result.add_info("scrcpy_server_jar", str(scrcpy_jar))
        # ファイルサイズも確認
        size_kb = scrcpy_jar.stat().st_size / 1024
        result.add_info("scrcpy_server_jar_size", f"{size_kb:.1f} KB")

    return result


def format_environment_report(result: EnvironmentCheckResult) -> str:
    """環境チェック結果をフォーマットして返す"""
    lines = []
    lines.append("")
    lines.append("=" * 70)
    lines.append("テスト環境チェック結果")
    lines.append("=" * 70)
    
    # 情報
    if result.info:
        lines.append("")
        lines.append("環境情報:")
        for key, value in result.info.items():
            lines.append(f"  {key}: {value}")
    
    # エラー
    if result.errors:
        lines.append("")
        lines.append("❌ エラー（テスト実行不可）:")
        for i, error in enumerate(result.errors, 1):
            lines.append(f"")
            lines.append(f"  [{i}] {error}")
    
    # 警告
    if result.warnings:
        lines.append("")
        lines.append("⚠️  警告:")
        for warning in result.warnings:
            lines.append(f"  - {warning}")
    
    # 結果サマリ
    lines.append("")
    if result.passed:
        lines.append("✅ テスト環境は正常です")
    else:
        lines.append("❌ テスト環境に問題があります。上記のエラーを修正してください。")
    
    lines.append("=" * 70)
    lines.append("")
    
    return "\n".join(lines)


def pytest_configure(config: pytest.Config) -> None:
    """pytest 起動時に環境チェックを実行"""
    # 環境チェックをスキップするオプション（CI 等で使用）
    if os.environ.get("SKIP_ENV_CHECK") == "1":
        return

    result = check_test_environment()
    report = format_environment_report(result)
    
    # 常にレポートを表示
    print(report, file=sys.stderr)
    
    if not result.passed:
        pytest.exit(
            "テスト環境が整っていません。上記のエラーを修正してから再実行してください。",
            returncode=1,
        )


# =============================================================================
# ユーティリティ関数
# =============================================================================

def get_connected_devices() -> list[str]:
    """adb devices で接続中のデバイスシリアルを取得"""
    result = subprocess.run(
        ["adb", "devices"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    lines = result.stdout.strip().split("\n")[1:]
    devices = []
    for line in lines:
        if "\tdevice" in line:
            serial = line.split("\t")[0]
            devices.append(serial)
    return devices


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def anyio_backend():
    """pytest-anyio のバックエンド設定"""
    return "asyncio"


@pytest.fixture(scope="session")
def connected_devices() -> list[str]:
    """接続中のデバイスリスト"""
    return get_connected_devices()


@pytest.fixture(scope="session")
def first_device(connected_devices: list[str]) -> str:
    """最初のデバイス（なければスキップ）"""
    if not connected_devices:
        pytest.skip("No Android device connected")
    return connected_devices[0]
