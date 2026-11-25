"""操作チャネル(ScrcpyControlClient)のテスト.

前半は端末不要(制御メッセージの検証、scrcpy 3.x のバイト列、画面サイズの読み取り)。
後半は ANDROID_SERIAL と SCRCPY_SERVER_JAR を設定したときだけ実端末で動かす(設定アプリの検索欄をタップして文字を入れる)。
"""

import asyncio
import os
import re
import struct
import subprocess
import time

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
    # 1 ノッチ = 0x7FFF/16(サーバ側で 16 倍される)。16 ノッチで上限
    assert struct.unpack(">BiiHHhhi", encode_scroll(1, 2, 3, 4, 1.0))[6] == 0x7FFF // 16
    assert struct.unpack(">BiiHHhhi", encode_scroll(1, 2, 3, 4, -99))[6] == -0x7FFF
    assert encode_keycode(0, 66) == struct.pack(">BBiii", 0, 0, 66, 0, 0)
    assert encode_text("ab") == b"\x01\x00\x00\x00\x02ab"
    clip = encode_set_clipboard("日", paste=True)
    assert clip[0] == 9 and clip[9] == 1 and clip[14:] == "日".encode()


def test_display_size_from_dumpsys():
    assert parse_display_size("  init=2560x1600 420dpi cur=1600x2560 app=1600x2464") == (1600, 2560)
    # 仮想ディスプレイが先に並んでも主ディスプレイ(mDisplayId=0)を使う(実機の出力の形)
    two = ("Display: mDisplayId=17\n    init=1080x672 1dpi cur=1080x672 app=1080x672\n"
           "Display: mDisplayId=0 (organized)\n    init=2560x1600 320dpi cur=2560x1600 app=2560x1600\n")
    assert parse_display_size(two) == (2560, 1600)
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
    for _ in range(5):  # 起動直後の uiautomator dump は "null root node" で空になることがある
        _adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
        for n in re.findall(r"<node [^>]*>", _adb("shell", "cat", "/sdcard/ui.xml")):
            if rid in n:
                x1, y1, x2, y2 = map(int, re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', n).groups())
                return (x1 + x2) / 2, (y1 + y2) / 2
        time.sleep(1)
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
        self.sent, self.fail_after, self.closed = [], fail_after, False

    def is_closing(self):
        return self.closed

    def close(self):
        self.closed = True

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


def _offline_client(tmp_path, dumpsys="Display: mDisplayId=0\n  cur=1000x2000\n"):
    jar = tmp_path / "s.jar"
    jar.write_bytes(b"")
    ctl = ScrcpyControlClient("dummy", str(jar))
    ctl._writer, ctl._size = _FakeWriter(), (100, 100)
    calls = []

    async def fake_adb(*args):
        calls.append(args)
        return dumpsys if "dumpsys" in args else ""

    ctl._adb = fake_adb
    return ctl, calls


async def test_pointer_down_rereads_display_size_and_scales(tmp_path):
    ctl, calls = _offline_client(tmp_path)
    assert (await ctl.handle({"type": "pointer", "action": "down", "x": 0.5, "y": 1.0, "seq": 3})) == {"type": "ack", "seq": 3, "ok": True}
    # 先に今のサイズで送り(dumpsys を待たない)、裏で取り直してサイズが変わっていたので新しいサイズで送り直す
    await ctl._refresh_task
    assert ctl._writer.sent == [encode_touch("down", 50, 99, 100, 100), encode_touch("down", 500, 1999, 1000, 2000)]
    await ctl.handle({"type": "pointer", "action": "move", "x": 0.1, "y": 0.1})
    assert sum("dumpsys" in c for c in calls) == 1  # move では取り直さない
    await ctl.handle({"type": "pointer", "action": "down", "x": 0.5, "y": 0.5})
    await ctl._refresh_task
    assert ctl._writer.sent[-1] == encode_touch("down", 500, 1000, 1000, 2000)  # サイズが同じなら送り直さない
    assert ctl._writer.sent[-2] == encode_touch("move", 100, 200, 1000, 2000)


async def test_finished_gesture_during_size_refresh_is_not_replayed(tmp_path):
    ctl, _ = _offline_client(tmp_path)
    gate = asyncio.Event()
    adb = ctl._adb

    async def slow_adb(*args):
        await gate.wait()  # dumpsys が遅い間に up まで届く
        return await adb(*args)

    ctl._adb = slow_adb
    await ctl.handle({"type": "pointer", "action": "down", "x": 0.5, "y": 0.5})
    await ctl.handle({"type": "pointer", "action": "move", "x": 0.5, "y": 0.2})
    await ctl.handle({"type": "pointer", "action": "up", "x": 0.5, "y": 0.1})  # dumpsys を待たずに送れる
    assert len(ctl._writer.sent) == 3
    gate.set()
    await ctl._refresh_task
    # 離し終えたジェスチャーは送り直さない(そのタップで回転した場合に二重タップになる)
    assert len(ctl._writer.sent) == 3 and ctl._size == (1000, 2000)


async def test_invalid_message_returns_error_without_sending(tmp_path):
    ctl, _ = _offline_client(tmp_path)
    r = await ctl.handle({"type": "key", "key": "F1", "seq": 9})
    assert r["type"] == "error" and r["seq"] == 9 and ctl._writer.sent == []


async def test_stop_clears_clipboard_left_dirty(tmp_path):
    ctl, _ = _offline_client(tmp_path)
    ctl._clipboard_dirty = True  # 貼り付け後に消せなかった状態
    writer = ctl._writer
    writer.close = lambda: None

    async def wait_closed():
        pass

    writer.wait_closed = wait_closed
    await ctl.stop()
    assert writer.sent[-1] == encode_set_clipboard("", paste=False)
    assert ctl._clipboard_dirty is False


async def test_size_refresh_failure_keeps_last_size(tmp_path):
    ctl, _ = _offline_client(tmp_path, dumpsys="garbage")
    r = await ctl.handle({"type": "pointer", "action": "down", "x": 0.5, "y": 0.5})
    await ctl._refresh_task
    assert r["ok"] and ctl._writer.sent == [encode_touch("down", 50, 50, 100, 100)]


async def test_stop_releases_held_touch_and_tolerates_dead_server(tmp_path):
    ctl, _ = _offline_client(tmp_path)
    await ctl.handle({"type": "pointer", "action": "move", "x": 0.2, "y": 0.3})
    writer = ctl._writer
    writer.close = lambda: None

    async def wait_closed():
        pass

    writer.wait_closed = wait_closed

    class _Dead:
        returncode = 1

        def terminate(self):
            raise ProcessLookupError

    ctl._server = _Dead()
    await ctl.stop()  # 終わったプロセスでも例外にしない
    assert writer.sent[-1] == encode_touch("up", 20, 30, 100, 100)


async def test_only_the_held_gesture_is_replayed_after_size_change(tmp_path):
    ctl, _ = _offline_client(tmp_path)
    gate = asyncio.Event()
    adb = ctl._adb

    async def slow_adb(*args):
        await gate.wait()
        return await adb(*args)

    ctl._adb = slow_adb
    await ctl.handle({"type": "wheel", "x": 0.5, "y": 0.5, "dy": 1})  # これが取り直しのきっかけ
    for a in ("down", "up", "down", "move"):  # 取り直し中のタップと、押したままのドラッグ
        await ctl.handle({"type": "pointer", "action": a, "x": 0.1, "y": 0.1})
    gate.set()
    await ctl._refresh_task
    # 押したままのドラッグだけを送り直す(済んだタップと wheel は二重にしない)
    assert ctl._writer.sent[5:] == [encode_touch(a, 100, 200, 1000, 2000) for a in ("down", "move")]


async def test_server_eof_makes_later_sends_fail(tmp_path):
    """端末側のサーバが終わったら、以後の入力を ok で返さず失敗させる(接続を閉じて端末の枠を空けさせる)."""
    jar = tmp_path / "s.jar"
    jar.write_bytes(b"")
    ctl = ScrcpyControlClient("dummy", str(jar))
    reader = asyncio.StreamReader()
    reader.feed_eof()
    ctl._reader, ctl._writer, ctl._size = reader, _FakeWriter(), (100, 100)
    await ctl._drain()
    with pytest.raises(RuntimeError):
        await ctl.handle({"type": "key", "key": "Enter"})


def test_control_jar_does_not_share_the_stream_jar_path():
    """映像側と同じ端末へ同時に push するので、同じパスに書き合わない."""
    from android_screen_stream.client import ScrcpyClient
    assert ScrcpyControlClient.DEVICE_JAR_PATH != ScrcpyClient.DEVICE_JAR_PATH
