"""
ScrcpyControlClient - クライアント(ブラウザ)からのタッチ・キー・文字を Android 端末へ注入する操作チャネル

配信(ScrcpyClient / StreamSession)とは別の scrcpy-server を、映像なし(video=false)・操作あり(control=true)・
固有の scid で起動する。配信の起動方法・ソケット名(固定の "scrcpy")には触れないので、既存の配信や録画に影響しない
(配信中に同時起動してタップ・文字が効き、配信が止まらないことを実機エミュレータで確認済み)。

制御メッセージ(JSON)は web-screen-stream と同じ形:
  {"type": "pointer", "action": "down"|"move"|"up", "x": 0..1, "y": 0..1}   # 表示中の映像に対する比率
  {"type": "wheel", "x": 0..1, "y": 0..1, "dy": -10..10}
  {"type": "key", "key": "Enter"|"Backspace"|"Tab"|"Escape"|"ArrowLeft"|... }
  {"type": "text", "text": "..."}

注意:
- 映像が無いと scrcpy は端末の「今の向きの」画面サイズと一致しない座標を黙って捨てる。そのため画面サイズを
  `dumpsys window displays` の cur= から取り、ポインタの down / wheel のたびに取り直す(回転に追従する)。
- scrcpy の INJECT_TEXT は ASCII 以外を入れられない。ASCII 以外は SET_CLIPBOARD(paste) で貼り付け、
  直後にクリップボードを空にする(秘密の値が端末のクリップボードに残らないようにする)。
- 入力した文字の内容はログに出さない。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import socket
import struct
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MAX_TEXT_LEN = 256
CONNECT_TIMEOUT = 8.0
ADB_TIMEOUT = 15.0

# Android KeyEvent のキーコード
_KEYCODES = {
    "Enter": 66, "Backspace": 67, "Tab": 61, "Escape": 111, "Delete": 112,
    "ArrowLeft": 21, "ArrowRight": 22, "ArrowUp": 19, "ArrowDown": 20,
    "Home": 122, "End": 123,
}

# scrcpy 3.x の制御メッセージ種別
_MSG_INJECT_KEYCODE, _MSG_INJECT_TEXT, _MSG_INJECT_TOUCH, _MSG_INJECT_SCROLL = 0, 1, 2, 3
_MSG_SET_CLIPBOARD = 9


class ControlError(ValueError):
    """制御メッセージが不正(型・範囲・未知の種別)."""


def parse_control_message(msg: object) -> dict:
    """制御メッセージを検証して正規化する(web-screen-stream の同名関数と同じ規則)."""
    if not isinstance(msg, dict):
        raise ControlError("message must be an object")
    kind = msg.get("type")
    if kind in ("pointer", "wheel"):
        x, y = msg.get("x"), msg.get("y")
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= v <= 1.0 for v in (x, y)):
            raise ControlError("x/y must be numbers in 0..1")
        if kind == "pointer":
            if msg.get("action") not in ("down", "move", "up"):
                raise ControlError("action must be down/move/up")
            return {"type": kind, "action": msg["action"], "x": float(x), "y": float(y)}
        dy = msg.get("dy")
        if not isinstance(dy, int) or isinstance(dy, bool) or not -10 <= dy <= 10:
            raise ControlError("dy must be an int in -10..10")
        return {"type": kind, "x": float(x), "y": float(y), "dy": dy}
    if kind == "key":
        if msg.get("key") not in _KEYCODES:
            raise ControlError(f"unsupported key: {msg.get('key')!r}")
        return {"type": kind, "key": msg["key"]}
    if kind == "text":
        text = msg.get("text")
        if not isinstance(text, str) or not text or len(text) > MAX_TEXT_LEN:
            raise ControlError(f"text must be a non-empty string up to {MAX_TEXT_LEN} chars")
        return {"type": kind, "text": text}
    raise ControlError(f"unknown type: {kind!r}")


def parse_display_size(dumpsys: str) -> tuple[int, int]:
    """`dumpsys window displays` の出力から、主ディスプレイ(mDisplayId=0)の今の向きの画面サイズ(cur=WxH)を取り出す.

    仮想ディスプレイ(画面共有・他ツールが作るもの)が先に並ぶことがあるため、最初の cur= ではなく
    mDisplayId=0 の区画の cur= を使う(UI 組み込みの確認で、先頭の仮想ディスプレイ 1080x672 を読んでタップが捨てられた)。
    """
    blocks = re.split(r"(?=Display: mDisplayId=)", dumpsys)
    main = next((b for b in blocks if re.match(r"Display: mDisplayId=0\b", b)), dumpsys)
    m = re.search(r"\bcur=(\d+)x(\d+)", main)
    if not m:
        raise RuntimeError("could not read current display size (cur=WxH) from dumpsys window displays")
    return int(m.group(1)), int(m.group(2))


def encode_touch(action: str, x: int, y: int, w: int, h: int) -> bytes:
    code = {"down": 0, "up": 1, "move": 2}[action]
    pressure = 0 if code == 1 else 0xFFFF
    buttons = 0 if code == 1 else 1  # AMOTION_EVENT_BUTTON_PRIMARY
    return struct.pack(">BBqiiHHHII", _MSG_INJECT_TOUCH, code, -2, x, y, w, h, pressure, 1, buttons)


def encode_scroll(x: int, y: int, w: int, h: int, vscroll: float) -> bytes:
    """vscroll はノッチ数(-16..16). scrcpy 2.x/3.x のサーバは i16 固定小数を 16 倍して読むので、16 で割って送る."""
    v = max(-1.0, min(1.0, vscroll / 16))
    return struct.pack(">BiiHHhhi", _MSG_INJECT_SCROLL, x, y, w, h, 0, int(v * 0x7FFF), 0)


def encode_keycode(action: int, keycode: int) -> bytes:
    return struct.pack(">BBiii", _MSG_INJECT_KEYCODE, action, keycode, 0, 0)


def encode_text(text: str) -> bytes:
    b = text.encode()
    return struct.pack(">BI", _MSG_INJECT_TEXT, len(b)) + b


def encode_set_clipboard(text: str, paste: bool) -> bytes:
    b = text.encode()
    return struct.pack(">BqBI", _MSG_SET_CLIPBOARD, 0, 1 if paste else 0, len(b)) + b


class ScrcpyControlClient:
    """映像なしの scrcpy-server へ制御メッセージを送る. 1 端末につき同時に 1 つだけ使う想定.

    Examples:
        async with ScrcpyControlClient("emulator-5554", server_jar="scrcpy-server.jar") as ctl:
            await ctl.handle({"type": "pointer", "action": "down", "x": 0.5, "y": 0.5})
    """

    DEVICE_JAR_PATH = "/data/local/tmp/scrcpy-server.jar"
    SERVER_VERSION = "3.3.4"

    def __init__(self, serial: str, server_jar: str, *, connect_host: Optional[str] = None, local_port: int = 0):
        self.serial = serial
        self.server_jar = Path(server_jar)
        if not self.server_jar.exists():
            raise FileNotFoundError(f"Server jar not found: {self.server_jar}")
        self.connect_host = connect_host or os.environ.get("SCRCPY_CONNECT_HOST", "localhost")
        self.local_port = local_port or self._free_port()
        self.scid = secrets.token_hex(4)  # 31bit 以内の 8 桁 16 進(scrcpy の scid 形式)
        self.scid = f"{int(self.scid, 16) & 0x7FFFFFFF:08x}"
        self._server: Optional[asyncio.subprocess.Process] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._drain_task: Optional[asyncio.Task] = None
        self._size: tuple[int, int] = (0, 0)
        self._lock = asyncio.Lock()
        self._clipboard_dirty = False  # 秘密を貼り付けた後、まだクリップボードを消せていない
        self._down: Optional[tuple[int, int]] = None  # 押したまま(up を送っていない)の位置
        self._refresh_task: Optional[asyncio.Task] = None
        self._pending: list[dict] = []  # 取り直し中に送った pointer / wheel(サイズが変わっていたら順に全部送り直す)

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    async def _adb(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "adb", "-s", self.serial, *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=ADB_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"adb {' '.join(args[:2])} timed out")
        if proc.returncode:
            raise RuntimeError(f"adb {' '.join(args[:2])} failed: {err.decode().strip()}")
        return out.decode()

    async def refresh_size(self) -> tuple[int, int]:
        self._size = parse_display_size(await self._adb("shell", "dumpsys", "window", "displays"))
        return self._size

    async def start(self) -> None:
        try:
            await self._adb("push", str(self.server_jar), self.DEVICE_JAR_PATH)
            await self._adb("forward", f"tcp:{self.local_port}", f"localabstract:scrcpy_{self.scid}")
            self._server = await asyncio.create_subprocess_exec(
                "adb", "-s", self.serial, "shell",
                f"CLASSPATH={self.DEVICE_JAR_PATH}", "app_process", "/", "com.genymobile.scrcpy.Server",
                self.SERVER_VERSION, f"scid={self.scid}", "tunnel_forward=true",
                "video=false", "audio=false", "control=true", "cleanup=false",
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(self._connect(), timeout=CONNECT_TIMEOUT)
            await self.refresh_size()
            # 端末側からのメッセージ(クリップボード同期など)を読み捨てる。読まないと送信側のバッファが詰まる
            self._drain_task = asyncio.create_task(self._drain(), name=f"scrcpy-control-drain-{self.serial}")
            logger.info("control channel started for %s (scid=%s, size=%s)", self.serial, self.scid, self._size)
        except BaseException:
            await self.stop()
            raise

    async def _connect(self) -> None:
        while True:
            try:
                reader, writer = await asyncio.open_connection(self.connect_host, self.local_port)
            except OSError:
                await asyncio.sleep(0.2)
                continue
            try:
                dummy = await asyncio.wait_for(reader.readexactly(1), timeout=2)
            except (asyncio.IncompleteReadError, asyncio.TimeoutError, OSError):
                writer.close()
                await asyncio.sleep(0.2)
                continue
            if dummy == b"\x00":  # forward モードでは最初のソケットにダミー 1 バイトが来る
                await reader.readexactly(64)  # 端末名(device meta)
                self._reader, self._writer = reader, writer
                return
            writer.close()

    async def _drain(self) -> None:
        try:
            while self._reader and await self._reader.read(4096):
                pass
        except (OSError, asyncio.CancelledError):
            pass

    async def _send(self, data: bytes) -> None:
        if not self._writer:
            raise RuntimeError("control channel is not started")
        self._writer.write(data)
        await self._writer.drain()

    def _xy(self, nx: float, ny: float) -> tuple[int, int]:
        w, h = self._size
        return min(int(nx * w), w - 1), min(int(ny * h), h - 1)

    async def handle(self, raw: object) -> dict:
        """制御メッセージを 1 件処理し、応答を返す. 不正なメッセージは error 応答(接続は切らない)."""
        seq = raw.get("seq") if isinstance(raw, dict) else None
        try:
            m = parse_control_message(raw)
        except ControlError as e:
            return {"type": "error", "seq": seq, "error": str(e)}
        refreshing = bool(self._refresh_task and not self._refresh_task.done())
        async with self._lock:
            await self._inject(m)
            if refreshing and m["type"] in ("pointer", "wheel"):
                self._pending.append(m)
        if (m["type"] == "wheel" or m.get("action") == "down") and not refreshing:
            self._pending = [m]
            # 回転に追従する(映像が無いので自分で取る)。adb(dumpsys)を待つと後続の move/up も遅れて
            # タップが長押しになるので、裏で取り直す
            self._refresh_task = asyncio.create_task(self._refresh_and_replay())
        logger.debug("control %s", m["type"])  # 内容(text)は出さない
        return {"type": "ack", "seq": seq, "ok": True}

    async def _refresh_and_replay(self) -> None:
        """画面サイズを取り直し、変わっていれば(古いサイズの操作は scrcpy が捨てたので)取り直し中の操作を送り直す."""
        before = self._size
        try:
            await self.refresh_size()
        except RuntimeError:
            logger.warning("could not refresh display size on %s; using %s", self.serial, before)
            return
        if self._size == before:
            return
        try:
            async with self._lock:
                # 取り直しのきっかけ以降に送った pointer / wheel(どれも古いサイズで捨てられた)を順に送り直す
                for e in self._pending:
                    await self._inject(e)
        except (OSError, RuntimeError):
            logger.warning("could not replay input after display size change on %s", self.serial)

    async def _inject(self, m: dict) -> None:
        w, h = self._size
        if m["type"] == "pointer":
            xy = self._xy(m["x"], m["y"])
            await self._send(encode_touch(m["action"], *xy, w, h))
            self._down = None if m["action"] == "up" else xy
        elif m["type"] == "wheel":
            x, y = self._xy(m["x"], m["y"])
            for _ in range(abs(m["dy"])):
                await self._send(encode_scroll(x, y, w, h, -1.0 if m["dy"] > 0 else 1.0))
        elif m["type"] == "key":
            code = _KEYCODES[m["key"]]
            await self._send(encode_keycode(0, code) + encode_keycode(1, code))
        elif m["text"].isascii():
            await self._send(encode_text(m["text"]))
        else:
            self._clipboard_dirty = True
            try:
                await self._send(encode_set_clipboard(m["text"], paste=True))
                await asyncio.sleep(0.3)  # 貼り付けが終わってから消す
            finally:
                # キャンセル・例外でも必ず消す(秘密の値を端末のクリップボードに残さない)
                await asyncio.shield(self._clear_clipboard())

    async def _clear_clipboard(self) -> None:
        try:
            await self._send(encode_set_clipboard("", paste=False))
            self._clipboard_dirty = False
        except (OSError, RuntimeError):
            logger.warning("could not clear device clipboard on %s", self.serial)

    async def stop(self) -> None:
        if self._refresh_task:
            self._refresh_task.cancel()
            self._refresh_task = None
        if self._down and self._writer:
            try:  # 押したまま切れた場合、端末に指が残らないように離す
                await self._send(encode_touch("up", *self._down, *self._size))
            except (OSError, RuntimeError):
                pass
            self._down = None
        if self._clipboard_dirty and self._writer:
            await self._clear_clipboard()  # 貼り付け後に消せていない場合の最後の機会
        if self._drain_task:
            self._drain_task.cancel()
            self._drain_task = None
        if self._writer:
            self._writer.close()
            try:
                await asyncio.wait_for(self._writer.wait_closed(), timeout=3)
            except (asyncio.TimeoutError, OSError):
                pass
            self._writer = self._reader = None
        if self._server:
            try:
                if self._server.returncode is None:
                    self._server.terminate()
                    try:
                        await asyncio.wait_for(self._server.wait(), timeout=3)
                    except asyncio.TimeoutError:
                        self._server.kill()
            except ProcessLookupError:
                pass  # 既に終わっている(端末が抜けた・scrcpy が落ちた)
            self._server = None
        try:
            await self._adb("forward", "--remove", f"tcp:{self.local_port}")
        except RuntimeError:
            pass  # forward が既に無い(start 途中の失敗など)

    async def __aenter__(self) -> "ScrcpyControlClient":
        await self.start()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.stop()
