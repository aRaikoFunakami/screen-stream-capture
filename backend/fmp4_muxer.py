"""fMP4 Muxer - tail -f + ffmpeg で成長中ファイルを fMP4 に変換

scrcpy が通常ファイルに書き込む Matroska (mkv) を tail -f で追いかけ、
ffmpeg で MSE 互換の fragmented MP4 を stdout に出力する。

Note: mp4形式はmoov atomがファイル末尾のため録画中は読み取り不可。
      mkv形式はストリーミング向け設計で部分読み取りが可能。
"""

import asyncio
import logging
from pathlib import Path
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)


class Fmp4Muxer:
    """tail -f + ffmpeg で成長中の mkv を fMP4 に変換

    scrcpy の録画ファイルを tail -f で追いかけながら
    ffmpeg にパイプし、fMP4 を stdout に出力する。
    シェルパイプラインを使用して uvloop との互換性を確保。
    """

    def __init__(self, record_path: Path, fps: int = 10):
        self.record_path = record_path
        self.fps = fps
        self._process: Optional[asyncio.subprocess.Process] = None
        self._running = False

    async def start(self) -> None:
        """tail -f | ffmpeg パイプラインを起動"""
        if self._running:
            return

        # ファイルが存在し、データが書き込まれるまで待機（最大 30 秒）
        # scrcpy はフラッシュに時間がかかるため、サイズ > 0 を確認
        logger.info(f"Waiting for record file: {self.record_path}")
        for i in range(300):  # 30秒
            if self.record_path.exists() and self.record_path.stat().st_size > 0:
                logger.info(f"Record file ready: {self.record_path.stat().st_size} bytes")
                break
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError(f"Record file not ready after 30s: {self.record_path}")

        # シェルパイプラインとして実行（uvloop 互換）
        # まずは手動で動作確認できた構成に極力寄せて、余計な低遅延フラグを付けない。
        shell_cmd = (
            f"tail -c +1 -f '{self.record_path}' | "
            f"ffmpeg -hide_banner -loglevel error -nostdin "
            f"-i pipe:0 "
            f"-an "
            f"-vf fps={self.fps} "
            f"-c:v libx264 -preset ultrafast -tune zerolatency "
            f"-g {self.fps} -keyint_min {self.fps} -sc_threshold 0 "
            f"-f mp4 -movflags frag_keyframe+empty_moov+default_base_moof "
            f"pipe:1"
        )
        logger.info(f"Starting muxer pipeline: {shell_cmd}")

        self._process = await asyncio.create_subprocess_shell(
            shell_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._running = True

        # stderr を非同期でログ出力
        asyncio.create_task(self._log_stderr())

        logger.info(f"fMP4 muxer pipeline started (PID: {self._process.pid})")

    async def stop(self) -> None:
        """パイプラインを停止"""
        self._running = False

        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                pass

        self._process = None
        logger.info("fMP4 muxer pipeline stopped")

    async def read_stream(self) -> AsyncGenerator[bytes, None]:
        """fMP4 ストリームを読み取り"""
        if not self._process or not self._process.stdout:
            raise RuntimeError("muxer is not running")

        try:
            while self._running:
                chunk = await self._process.stdout.read(4096)  # 4KB chunks (low latency)
                if not chunk:
                    break
                yield chunk
        except Exception as e:
            logger.error(f"Error reading muxer output: {e}")

    async def _log_stderr(self) -> None:
        """stderr をログに出力"""
        if not self._process or not self._process.stderr:
            return

        try:
            async for line in self._process.stderr:
                text = line.decode(errors="replace").strip()
                if text:
                    logger.warning(f"muxer: {text}")
        except Exception:
            pass

    @property
    def is_running(self) -> bool:
        """パイプラインが実行中か"""
        return self._running and self._process is not None
