"""Server-side JPEG capture service.

This module implements the "capture WS" design described in
work/multi_device_stream_and_capture/plan.md.

- A capture client connects to `WS /api/ws/capture/{serial}`.
- While at least one capture client is connected for a device, the backend keeps a
  decoder running (ffmpeg) and continuously updates the latest JPEG in memory.
- On a capture request, the backend immediately returns the latest JPEG bytes.

Implementation note:
- We use an ffmpeg process that takes raw H.264 (Annex B) on stdin and outputs a
  continuous MJPEG stream on stdout. We parse JPEG SOI/EOI markers to extract
  individual JPEG images.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from android_screen_stream import StreamManager

logger = logging.getLogger(__name__)


def _extract_complete_jpegs(buf: bytearray) -> list[bytes]:
    """Extract complete JPEG frames from an MJPEG byte buffer.

    The function mutates `buf` in-place, removing consumed bytes and returning a
    list of complete JPEG images (each includes SOI/EOI markers).
    """

    frames: list[bytes] = []

    while True:
        start = buf.find(b"\xff\xd8")
        if start < 0:
            # Keep the tail in case we split the marker.
            if len(buf) > 2:
                del buf[:-2]
            break

        end = buf.find(b"\xff\xd9", start + 2)
        if end < 0:
            # Keep from SOI.
            if start > 0:
                del buf[:start]
            break

        frames.append(bytes(buf[start : end + 2]))
        del buf[: end + 2]

    return frames


def _quality_percent_to_mjpeg_qscale(quality: int) -> int:
    """Map a 1-100 quality percent to ffmpeg mjpeg qscale (2-31).

    ffmpeg MJPEG uses `-q:v` as a *quality scale* where smaller is better.
    We accept a more familiar 1..100 (larger is better) and convert.
    """

    q = int(quality)
    if q < 1:
        q = 1
    if q > 100:
        q = 100

    # 1 -> 31 (worst), 100 -> 2 (best)
    return int(round(31 - (q - 1) * (29 / 99)))


@dataclass(frozen=True)
class CaptureResult:
    """Metadata for a single capture."""

    capture_id: str
    captured_at: str
    serial: str
    bytes: int
    path: Optional[str]


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

        self._mjpeg_qscale = _quality_percent_to_mjpeg_qscale(self._default_quality)

        self._refcount = 0
        self._ref_lock = asyncio.Lock()

        self._proc: Optional[asyncio.subprocess.Process] = None
        self._task_feed: Optional[asyncio.Task[None]] = None
        self._task_read: Optional[asyncio.Task[None]] = None

        self._seq = 0
        self._latest_jpeg: Optional[bytes] = None
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

        # NOTE: In this initial implementation the worker produces a continuous MJPEG
        # stream at a fixed quality. We accept `quality` for forward compatibility.
        if quality is not None:
            _quality_percent_to_mjpeg_qscale(int(quality))

        async with self._encode_sem:
            jpeg = await self._get_latest_jpeg(timeout_sec=5.0)

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

    async def _get_latest_jpeg(self, *, timeout_sec: float) -> bytes:
        async with self._cond:
            if self._latest_jpeg is not None:
                # For "任意タイミング" semantics, try to wait for one newer frame.
                before = self._seq
                try:
                    await asyncio.wait_for(self._cond.wait_for(lambda: self._seq > before), timeout=0.5)
                except TimeoutError:
                    pass
                if self._latest_jpeg is not None:
                    return self._latest_jpeg

            await asyncio.wait_for(self._cond.wait_for(lambda: self._latest_jpeg is not None), timeout=timeout_sec)
            assert self._latest_jpeg is not None
            return self._latest_jpeg

    async def _start_decoder(self) -> None:
        if self._proc is not None:
            return

        logger.info(f"Starting capture decoder for {self.serial}")

        # NOTE: ffmpeg must be installed in the runtime environment.
        # We output MJPEG frames continuously; JPEG boundaries are detected by SOI/EOI markers.
        args = [
            "ffmpeg",
            "-loglevel",
            "error",
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
            "-f",
            "mjpeg",
            "-q:v",
            str(self._mjpeg_qscale),
            "pipe:1",
        ]

        self._proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        self._task_feed = asyncio.create_task(self._feed_h264_loop(), name=f"capture-feed-{self.serial}")
        self._task_read = asyncio.create_task(self._read_mjpeg_loop(), name=f"capture-read-{self.serial}")

    async def _stop_decoder(self) -> None:
        if self._proc is None:
            return

        logger.info(f"Stopping capture decoder for {self.serial}")

        for task in (self._task_feed, self._task_read):
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

    async def _read_mjpeg_loop(self) -> None:
        assert self._proc is not None
        assert self._proc.stdout is not None

        buf = bytearray()

        try:
            while True:
                chunk = await self._proc.stdout.read(64 * 1024)
                if not chunk:
                    break

                buf.extend(chunk)

                for frame in _extract_complete_jpegs(buf):
                    async with self._cond:
                        self._latest_jpeg = frame
                        self._seq += 1
                        self._cond.notify_all()

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Capture read loop error for {self.serial}: {e}")


class CaptureManager:
    """Manages capture decoders per device."""

    def __init__(
        self,
        *,
        stream_manager: "StreamManager",
        output_dir: str,
    ) -> None:
        self._stream_manager = stream_manager
        self._output_dir = output_dir

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


_capture_manager: Optional[CaptureManager] = None


def get_capture_manager(*, stream_manager: "StreamManager", output_dir: str) -> CaptureManager:
    """CaptureManager のシングルトンインスタンスを取得"""

    global _capture_manager
    if _capture_manager is None:
        _capture_manager = CaptureManager(stream_manager=stream_manager, output_dir=output_dir)
    return _capture_manager
