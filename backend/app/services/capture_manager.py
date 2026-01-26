"""Server-side JPEG capture service.

This module implements the "capture WS" design described in
work/multi_device_stream_and_capture/plan.md.

- A capture client connects to `WS /api/ws/capture/{serial}`.
- While at least one capture client is connected for a device, the backend keeps a
    decoder running (ffmpeg) and continuously updates the latest decoded frame in memory.
- On a capture request, the backend encodes that latest frame to JPEG and returns
    the JPEG bytes.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from android_screen_stream import StreamManager

logger = logging.getLogger(__name__)


_RE_DIM = re.compile(r"(?P<w>\d{2,5})x(?P<h>\d{2,5})")


def _quality_percent_to_mjpeg_qscale(quality: int) -> int:
    """Map a 1-100 quality percent to ffmpeg mjpeg qscale (2-31)."""

    q = int(quality)
    if q < 1:
        q = 1
    if q > 100:
        q = 100
    # 1 -> 31 (worst), 100 -> 2 (best)
    return int(round(31 - (q - 1) * (29 / 99)))


def _yuv420p_frame_size(width: int, height: int) -> int:
    return (width * height * 3) // 2


@dataclass(frozen=True)
class CaptureResult:
    """Metadata for a single capture."""

    capture_id: str
    captured_at: str
    serial: str
    width: int
    height: int
    bytes: int
    path: Optional[str]


@dataclass(frozen=True)
class FrameBuffer:
    width: int
    height: int
    pix_fmt: str
    captured_at: str
    data: bytes


class CaptureWorker:
    def __init__(
        self,
        serial: str,
        *,
        stream_manager: "StreamManager",
        output_dir: str,
        default_quality: int = 80,
        decoder_fps: int = 30,
    ) -> None:
        self.serial = serial
        self._stream_manager = stream_manager
        self._output_dir = Path(output_dir)
        self._default_quality = default_quality
        self._decoder_fps = decoder_fps

        self._width: int | None = None
        self._height: int | None = None

        self._refcount = 0
        self._ref_lock = asyncio.Lock()

        self._proc: Optional[asyncio.subprocess.Process] = None
        self._task_feed: Optional[asyncio.Task[None]] = None
        self._task_read: Optional[asyncio.Task[None]] = None
        self._task_stderr: Optional[asyncio.Task[None]] = None

        self._seq = 0
        self._latest_frame: Optional[FrameBuffer] = None
        self._cond = asyncio.Condition()

        self._encode_sem = asyncio.Semaphore(1)

    @property
    def seq(self) -> int:
        return self._seq

    @property
    def refcount(self) -> int:
        return self._refcount

    async def acquire(self) -> None:
        async with self._ref_lock:
            self._refcount += 1
            if self._refcount == 1:
                await self._start_decoder()

    async def release(self) -> None:
        async with self._ref_lock:
            self._refcount = max(0, self._refcount - 1)
            if self._refcount == 0:
                await self._stop_decoder()

    async def capture_jpeg(self, *, quality: Optional[int], save: bool) -> tuple[CaptureResult, bytes]:
        """Return a JPEG image (bytes) and its metadata."""

        quality_percent = int(quality) if quality is not None else int(self._default_quality)
        qscale = _quality_percent_to_mjpeg_qscale(quality_percent)

        async with self._encode_sem:
            frame = await self._get_latest_frame(timeout_sec=5.0)
            jpeg = await self._encode_jpeg_with_ffmpeg(frame, qscale=qscale)

            capture_id = str(uuid4())
            captured_at = datetime.now(timezone.utc).isoformat()

            path: Optional[str] = None
            if save:
                path = await self._save_jpeg(capture_id=capture_id, captured_at=captured_at, jpeg=jpeg)

            return (
                CaptureResult(
                    capture_id=capture_id,
                    captured_at=captured_at,
                    serial=self.serial,
                    width=frame.width,
                    height=frame.height,
                    bytes=len(jpeg),
                    path=path,
                ),
                jpeg,
            )

    async def _save_jpeg(self, *, capture_id: str, captured_at: str, jpeg: bytes) -> str:
        out_dir = self._output_dir / self.serial
        out_dir.mkdir(parents=True, exist_ok=True)

        # Use a filesystem-friendly timestamp
        ts = captured_at.replace(":", "").replace("+", "").replace("Z", "")
        file_path = out_dir / f"{ts}_{capture_id}.jpg"

        # Avoid blocking event loop on file I/O.
        await asyncio.to_thread(file_path.write_bytes, jpeg)

        return str(file_path)

    async def _get_latest_frame(self, *, timeout_sec: float) -> FrameBuffer:
        async with self._cond:
            if self._latest_frame is not None:
                before = self._seq
                try:
                    await asyncio.wait_for(self._cond.wait_for(lambda: self._seq > before), timeout=0.5)
                except TimeoutError:
                    pass
                if self._latest_frame is not None:
                    return self._latest_frame

            await asyncio.wait_for(self._cond.wait_for(lambda: self._latest_frame is not None), timeout=timeout_sec)
            assert self._latest_frame is not None
            return self._latest_frame

    async def _encode_jpeg_with_ffmpeg(self, frame: FrameBuffer, *, qscale: int) -> bytes:
        """Encode a single YUV420P frame to JPEG using ffmpeg (on-demand)."""

        args = [
            "ffmpeg",
            "-loglevel",
            "error",
            "-nostdin",
            "-f",
            "rawvideo",
            "-pix_fmt",
            frame.pix_fmt,
            "-s",
            f"{frame.width}x{frame.height}",
            "-i",
            "pipe:0",
            "-frames:v",
            "1",
            "-f",
            "mjpeg",
            "-q:v",
            str(qscale),
            "pipe:1",
        ]

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        assert proc.stdin is not None
        assert proc.stdout is not None

        proc.stdin.write(frame.data)
        await proc.stdin.drain()
        proc.stdin.close()

        jpeg = await proc.stdout.read()
        with contextlib.suppress(Exception):
            await proc.wait()

        if not jpeg.startswith(b"\xff\xd8"):
            raise RuntimeError("Failed to encode JPEG")
        return jpeg

    async def _start_decoder(self) -> None:
        if self._proc is not None:
            return

        logger.info(f"Starting capture decoder for {self.serial}")

        # NOTE: ffmpeg must be installed in the runtime environment.
        # We decode continuously to rawvideo (yuv420p) and keep only the latest frame.
        args = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "info",
            "-nostats",
            "-nostdin",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-probesize",
            "32",
            "-analyzeduration",
            "0",
            "-f",
            "h264",
            "-i",
            "pipe:0",
            "-vf",
            f"fps={self._decoder_fps}",
            "-pix_fmt",
            "yuv420p",
            "-f",
            "rawvideo",
            "pipe:1",
        ]

        self._proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        self._task_feed = asyncio.create_task(self._feed_h264_loop(), name=f"capture-feed-{self.serial}")
        self._task_read = asyncio.create_task(self._read_rawvideo_loop(), name=f"capture-read-{self.serial}")
        self._task_stderr = asyncio.create_task(self._read_ffmpeg_stderr_loop(), name=f"capture-stderr-{self.serial}")

    async def _stop_decoder(self) -> None:
        if self._proc is None:
            return

        logger.info(f"Stopping capture decoder for {self.serial}")

        for task in (self._task_feed, self._task_read, self._task_stderr):
            if task is not None:
                task.cancel()

        with contextlib.suppress(Exception):
            if self._proc.stdin:
                self._proc.stdin.close()

        self._proc.terminate()
        try:
            await asyncio.wait_for(self._proc.wait(), timeout=3.0)
        except TimeoutError:
            self._proc.kill()
            await self._proc.wait()

        self._proc = None
        self._task_feed = None
        self._task_read = None
        self._task_stderr = None

    async def _feed_h264_loop(self) -> None:
        assert self._proc is not None
        assert self._proc.stdin is not None

        session = await self._stream_manager.get_or_create(self.serial)

        try:
            async for chunk in session.subscribe():
                if not chunk or self._proc is None:
                    break
                try:
                    self._proc.stdin.write(chunk)
                    await self._proc.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    break
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Capture feed loop error for {self.serial}: {e}")

    async def _read_ffmpeg_stderr_loop(self) -> None:
        assert self._proc is not None
        assert self._proc.stderr is not None

        try:
            while True:
                line = await self._proc.stderr.readline()
                if not line:
                    break

                text = line.decode("utf-8", errors="ignore")
                # Detect resolution once, but always keep draining stderr to avoid blocking ffmpeg.
                if self._width is None or self._height is None:
                    if "Video:" not in text:
                        continue
                    m = _RE_DIM.search(text)
                    if not m:
                        continue

                    w = int(m.group("w"))
                    h = int(m.group("h"))
                    if w <= 0 or h <= 0:
                        continue

                    self._width = w
                    self._height = h
                    logger.info(f"Capture decoder resolution for {self.serial}: {w}x{h}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Capture stderr loop error for {self.serial}: {e}")

    async def _read_rawvideo_loop(self) -> None:
        assert self._proc is not None
        assert self._proc.stdout is not None

        buf = bytearray()

        try:
            while True:
                chunk = await self._proc.stdout.read(256 * 1024)
                if not chunk:
                    break

                buf.extend(chunk)

                if self._width is None or self._height is None:
                    continue
                frame_size = _yuv420p_frame_size(self._width, self._height)
                if frame_size <= 0:
                    continue

                # Consume complete frames; keep only latest.
                latest: bytes | None = None
                while len(buf) >= frame_size:
                    latest = bytes(buf[:frame_size])
                    del buf[:frame_size]

                if latest is None:
                    continue

                fb = FrameBuffer(
                    width=self._width,
                    height=self._height,
                    pix_fmt="yuv420p",
                    captured_at=datetime.now(timezone.utc).isoformat(),
                    data=latest,
                )

                async with self._cond:
                    self._latest_frame = fb
                    self._seq += 1
                    self._cond.notify_all()

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Capture rawvideo loop error for {self.serial}: {e}")


class CaptureManager:
    """Manages capture decoders per device."""

    def __init__(
        self,
        *,
        stream_manager: "StreamManager",
        output_dir: str,
        default_quality: int = 80,
    ) -> None:
        self._stream_manager = stream_manager
        self._output_dir = output_dir
        self._default_quality = int(default_quality)

        self._workers: dict[str, CaptureWorker] = {}
        self._lock = asyncio.Lock()

    async def get_or_create_worker(self, serial: str) -> CaptureWorker:
        async with self._lock:
            worker = self._workers.get(serial)
            if worker is None:
                worker = CaptureWorker(
                    serial,
                    stream_manager=self._stream_manager,
                    output_dir=self._output_dir,
                    default_quality=self._default_quality,
                )
                self._workers[serial] = worker
            return worker

    async def acquire(self, serial: str) -> CaptureWorker:
        worker = await self.get_or_create_worker(serial)
        await worker.acquire()
        return worker

    async def release(self, serial: str) -> None:
        async with self._lock:
            worker = self._workers.get(serial)

        if worker is None:
            return

        await worker.release()

        # If it's fully released, drop it from registry.
        if worker.refcount == 0:
            async with self._lock:
                if self._workers.get(serial) is worker and worker.refcount == 0:
                    self._workers.pop(serial, None)

    async def stop_all(self) -> None:
        async with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()

        for worker in workers:
            with contextlib.suppress(Exception):
                # Force stop
                while worker.refcount > 0:
                    await worker.release()

    async def snapshot_running(self) -> dict[str, bool]:
        """Return a mapping of serial -> capture decoder running."""

        async with self._lock:
            workers = dict(self._workers)

        result: dict[str, bool] = {}
        for serial, worker in workers.items():
            result[serial] = bool(worker.refcount > 0)
        return result


_capture_manager: Optional[CaptureManager] = None


def get_capture_manager(
    *,
    stream_manager: "StreamManager",
    output_dir: str,
    default_quality: int = 80,
) -> CaptureManager:
    """CaptureManager のシングルトンインスタンスを取得"""

    global _capture_manager
    if _capture_manager is None:
        _capture_manager = CaptureManager(
            stream_manager=stream_manager,
            output_dir=output_dir,
            default_quality=default_quality,
        )
    return _capture_manager
