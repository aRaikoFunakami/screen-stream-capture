"""総合テスト用 conftest.py

このファイルは実際の実装を使った総合テストのための pytest fixtures を提供します。
モックは使用せず、実際のデバイス・scrcpy・ffmpeg を使用します。

前提条件:
- adb devices で少なくとも1台のデバイスが接続されていること
- scrcpy-server.jar が vendor/ に存在すること  
- ffmpeg がインストールされていること
"""

from __future__ import annotations

import subprocess

import pytest


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
