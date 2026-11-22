"""操作チャネル(ScrcpyControlClient)のテスト.

前半は端末不要(制御メッセージの検証、scrcpy 3.x のバイト列、画面サイズの読み取り)。
後半は ANDROID_SERIAL と SCRCPY_SERVER_JAR を設定したときだけ実端末で動かす(設定アプリの検索欄をタップして文字を入れる)。
"""

import asyncio
import os
import re
import struct
import subprocess

import pytest

from android_screen_stream.control import (
    ControlError, ScrcpyControlClient, encode_keycode, encode_scroll, encode_set_clipboard, encode_text,
    encode_touch, parse_control_message, parse_display_size,
)


def test_touch_layout_matches_scrcpy3():
    b = encode_touch("down", 10, 20, 1280, 800)
    assert len(b) == 32
    t, action, pid, x, y, w, h, pressure, abtn, btns = struct.unpack(">BBqiiHHHII", b)
    assert (t, action, pid, x, y, w, h, pressure, btns) == (2, 0, -2, 10, 20, 1280, 800, 0xFFFF, 1)
    assert struct.unpack(">BBqiiHHHII", encode_touch("up", 1, 1, 2, 2))[7] == 0


def test_other_layouts():
    assert len(encode_scroll(1, 2, 3, 4, -1.0)) == 21
    assert encode_keycode(0, 66) == struct.pack(">BBiii", 0, 0, 66, 0, 0)
    assert encode_text("ab") == b"\x01\x00\x00\x00\x02ab"
    clip = encode_set_clipboard("日", paste=True)
    assert clip[0] == 9 and clip[9] == 1 and clip[14:] == "日".encode()


def test_display_size_from_dumpsys():
    assert parse_display_size("  init=2560x1600 420dpi cur=1600x2560 app=1600x2464") == (1600, 2560)
    with pytest.raises(RuntimeError):
        parse_display_size("no size here")


@pytest.mark.parametrize("msg", [{"type": "text", "text": ""}, {"type": "key", "key": "F1"}, {"type": "pointer", "action": "down", "x": -0.1, "y": 0}])
def test_invalid_messages(msg):
    with pytest.raises(ControlError):
        parse_control_message(msg)


SERIAL = os.environ.get("ANDROID_SERIAL")
JAR = os.environ.get("SCRCPY_SERVER_JAR")


def _adb(*a):
    return subprocess.run(["adb", "-s", SERIAL, *a], capture_output=True, text=True, timeout=20).stdout


def _node_center(rid):
    _adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
    for n in re.findall(r"<node [^>]*>", _adb("shell", "cat", "/sdcard/ui.xml")):
        if rid in n:
            x1, y1, x2, y2 = map(int, re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', n).groups())
            return (x1 + x2) / 2, (y1 + y2) / 2
    raise AssertionError(f"{rid} not found")


@pytest.mark.skipif(not (SERIAL and JAR), reason="ANDROID_SERIAL / SCRCPY_SERVER_JAR not set")
async def test_tap_and_type_ascii_and_japanese_on_device():
    _adb("shell", "am", "force-stop", "com.android.settings")
    _adb("shell", "am", "start", "-W", "-a", "android.settings.SETTINGS")
    await asyncio.sleep(2)
    cx, cy = _node_center('resource-id="com.android.settings:id/search_bar_title"')
    async with ScrcpyControlClient(SERIAL, JAR) as ctl:
        w, h = ctl._size
        for action in ("down", "up"):
            assert (await ctl.handle({"type": "pointer", "action": action, "x": cx / w, "y": cy / h}))["ok"]
        await asyncio.sleep(2)
        assert "SearchActivity" in _adb("shell", "dumpsys", "activity", "activities").split("topResumedActivity=")[1].split("\n")[0]
        await ctl.handle({"type": "text", "text": "wifi"})
        await ctl.handle({"type": "text", "text": "日本"})
        await asyncio.sleep(1.5)
        _adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
        assert 'text="wifi日本"' in _adb("shell", "cat", "/sdcard/ui.xml")
    _adb("shell", "input", "keyevent", "HOME")


class _FakeWriter:
    def __init__(self, fail_after=None):
        self.sent, self.fail_after = [], fail_after

    def write(self, data):
        self.sent.append(data)

    async def drain(self):
        if self.fail_after is not None and len(self.sent) > self.fail_after:
            raise OSError("broken pipe")


async def test_clipboard_is_cleared_even_when_paste_is_cancelled(tmp_path):
    jar = tmp_path / "s.jar"
    jar.write_bytes(b"")
    ctl = ScrcpyControlClient("dummy", str(jar))
    ctl._writer, ctl._size = _FakeWriter(), (100, 100)
    task = asyncio.create_task(ctl.handle({"type": "text", "text": "秘密"}))
    await asyncio.sleep(0.05)  # 貼り付けを送って待っている最中に
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.05)
    assert ctl._writer.sent[-1] == encode_set_clipboard("", paste=False)
    assert ctl._clipboard_dirty is False
