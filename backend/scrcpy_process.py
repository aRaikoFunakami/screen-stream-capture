"""scrcpy プロセス管理 - 通常ファイルへ録画 + tail -f 方式

scrcpy v3 で stdout が使えないため、通常ファイルに録画し
tail -f で追いかけながら ffmpeg に渡す方式を採用。
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _safe_serial_for_path(serial: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in serial)


class ScrcpyRecorder:
    """scrcpy を起動し、通常ファイルに Matroska (mkv) を書き込ませる"""

    def __init__(
        self,
        serial: str,
        record_path: Optional[str] = None,
        video_codec: str = "h264",
        max_size: int = 1920,
        max_fps: int = 10,
        video_bit_rate: int = 2000000,
    ):
        self.serial = serial
        self.video_codec = video_codec
        self.max_size = max_size
        self.max_fps = max_fps
        self.video_bit_rate = video_bit_rate

        default_path = f"/tmp/screen-stream-capture_{_safe_serial_for_path(serial)}.mkv"
        self.record_path = Path(record_path or default_path)

        self._process: Optional[asyncio.subprocess.Process] = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            logger.warning(f"scrcpy recorder for {self.serial} is already running")
            return

        # 既存ファイルを削除
        self._cleanup_record_file()

        cmd = [
            "scrcpy",
            "-s", self.serial,
            "--no-playback",
            "--no-window",
            "--no-audio",
            f"--video-codec={self.video_codec}",
            f"--max-size={self.max_size}",
            f"--max-fps={self.max_fps}",
            f"--video-bit-rate={self.video_bit_rate}",
            f"--record={str(self.record_path)}",
        ]

        logger.info(f"Starting scrcpy recorder for {self.serial}: {' '.join(cmd)}")

        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        self._running = True

        asyncio.create_task(self._log_stderr())

        logger.info(f"scrcpy recorder started for {self.serial} (PID: {self._process.pid})")

    async def stop(self) -> None:
        self._running = False

        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                pass
            finally:
                self._process = None

        self._cleanup_record_file()
        logger.info(f"scrcpy recorder stopped for {self.serial}")

    def _cleanup_record_file(self) -> None:
        try:
            self.record_path.unlink(missing_ok=True)
        except Exception:
            pass

    async def _log_stderr(self) -> None:
        if not self._process or not self._process.stderr:
            return
        try:
            async for line in self._process.stderr:
                text = line.decode(errors="replace").strip()
                if text:
                    logger.info(f"scrcpy [{self.serial}]: {text}")
        except Exception:
            pass

    @property
    def is_running(self) -> bool:
        return self._running and self._process is not None


# 後方互換エイリアス
ScrcpyFifoRecorder = ScrcpyRecorder
ScrcpyProcess = ScrcpyRecorder
