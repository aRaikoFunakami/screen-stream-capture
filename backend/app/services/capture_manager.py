"""Server-side JPEG capture service.

This module implements the "capture WS" design described in
work/multi_device_stream_and_capture/plan.md.

- A capture client connects to `WS /api/ws/capture/{serial}`.
- While at least one capture client is connected for a device, the backend keeps a
    decoder running (ffmpeg) and continuously updates the latest decoded frame in memory.
- On a capture request, the backend encodes that latest frame to JPEG and returns
    the JPEG bytes.

パフォーマンス仕様:
    - 最初のキャプチャ: 約0.5〜1秒（デコーダ起動後、最初のフレームを待つため）
    - 2回目以降のキャプチャ: 約60〜120ms（フレーム取得 + JPEGエンコード）
    
    この遅延は、デコーダが起動直後でまだフレームが届いていない状態で
    キャプチャリクエストを受けた場合に発生します。
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


def _find_sps_nal_unit(data: bytes) -> bytes | None:
    """H.264データからSPS NAL unitを探す。解像度変更の検出に使用。"""
    i = 0
    while i < len(data) - 4:
        # NAL start code を探す (0x00 0x00 0x00 0x01 または 0x00 0x00 0x01)
        nal_start = -1
        if data[i] == 0 and data[i + 1] == 0 and data[i + 2] == 0 and data[i + 3] == 1:
            nal_start = i + 4
        elif data[i] == 0 and data[i + 1] == 0 and data[i + 2] == 1:
            nal_start = i + 3
        
        if nal_start >= 0 and nal_start < len(data):
            nal_type = data[nal_start] & 0x1f
            # NAL type 7 = SPS
            if nal_type == 7:
                # 次のstart codeまで、またはデータ終端までをSPSとして返す
                for j in range(nal_start, len(data) - 3):
                    if ((data[j] == 0 and data[j + 1] == 0 and data[j + 2] == 0 and data[j + 3] == 1) or
                        (data[j] == 0 and data[j + 1] == 0 and data[j + 2] == 1)):
                        return data[nal_start:j]
                return data[nal_start:]
        i += 1
    return None


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
        self._last_sps: bytes | None = None  # SPS変更検出用
        self._resolution_changed: bool = False  # 解像度変更フラグ

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
        import time
        t0 = time.perf_counter()

        quality_percent = int(quality) if quality is not None else int(self._default_quality)
        qscale = _quality_percent_to_mjpeg_qscale(quality_percent)

        async with self._encode_sem:
            t1 = time.perf_counter()
            frame = await self._get_latest_frame(timeout_sec=5.0)
            t2 = time.perf_counter()
            jpeg = await self._encode_jpeg_with_ffmpeg(frame, qscale=qscale)
            t3 = time.perf_counter()
            logger.info(
                f"Capture timing for {self.serial}: "
                f"sem_wait={t1-t0:.3f}s, get_frame={t2-t1:.3f}s, encode={t3-t2:.3f}s, total={t3-t0:.3f}s"
            )

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
        """キャプチャリクエスト時に最新フレームを取得する。
        
        重要: 既にフレームがある場合でも、必ず新しいフレームが来るまで待つ。
        これにより、キャプチャボタンを押した時点の画面が確実に取得される。
        """
        async with self._cond:
            # 現在のシーケンス番号を記録
            current_seq = self._seq
            
            # 新しいフレームが来るまで待つ（現在より大きいシーケンス番号）
            try:
                await asyncio.wait_for(
                    self._cond.wait_for(lambda: self._seq > current_seq and self._latest_frame is not None),
                    timeout=timeout_sec,
                )
            except TimeoutError:
                # タイムアウトした場合、既存フレームがあればそれを使用（フォールバック）
                if self._latest_frame is not None:
                    logger.warning(
                        f"Capture timeout waiting for new frame (seq={current_seq}), "
                        f"using existing frame (seq={self._seq})"
                    )
                    return self._latest_frame
                raise TimeoutError("No frame available for capture")
            
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
        # NOTE: fps フィルタは削除。入力フレームレートをそのまま使用し、遅延を最小化する。
        args = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "info",
            "-nostats",
            "-nostdin",
            # 入力オプション: バッファリングを最小化
            "-fflags",
            "+genpts+discardcorrupt",
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
            # 出力オプション: フレームを即座に出力
            "-vsync",
            "passthrough",
            "-pix_fmt",
            "yuv420p",
            "-f",
            "rawvideo",
            "-flush_packets",
            "1",
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

    async def _restart_decoder_for_resolution_change(self, first_chunk: bytes) -> None:
        """解像度変更時にffmpegデコーダを再起動する。"""
        logger.info(f"Restarting decoder for resolution change: {self.serial}")
        
        # 現在のffmpegプロセスを停止
        if self._proc is not None:
            with contextlib.suppress(Exception):
                if self._proc.stdin:
                    self._proc.stdin.close()
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=1.0)
            except TimeoutError:
                self._proc.kill()
                await self._proc.wait()
        
        # 状態をリセット
        self._proc = None
        self._width = None
        self._height = None
        self._latest_frame = None
        
        # タスクをキャンセル（読み取りタスクはプロセス終了で自動終了するはず）
        if self._task_read is not None:
            self._task_read.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task_read
            self._task_read = None
        if self._task_stderr is not None:
            self._task_stderr.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task_stderr
            self._task_stderr = None
        
        # 新しいffmpegプロセスを起動
        await self._start_decoder_process_only()
        
        # 最初のチャンク（SPSを含む）を書き込む
        if self._proc is not None and self._proc.stdin is not None:
            self._proc.stdin.write(first_chunk)
            await self._proc.stdin.drain()
            logger.info(f"Decoder restarted for {self.serial}, fed first chunk with new SPS")

    async def _start_decoder_process_only(self) -> None:
        """ffmpegプロセスのみを起動する（タスクは別途開始）。"""
        args = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "info",
            "-nostats",
            "-nostdin",
            "-f",
            "h264",
            "-i",
            "pipe:0",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "yuv420p",
            "pipe:1",
        ]

        logger.info(f"Starting decoder process for {self.serial}: {' '.join(args)}")

        self._proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # 読み取りタスクを開始
        self._task_read = asyncio.create_task(self._read_rawvideo_loop(), name=f"capture-read-{self.serial}")
        self._task_stderr = asyncio.create_task(self._read_ffmpeg_stderr_loop(), name=f"capture-stderr-{self.serial}")

    async def _feed_h264_loop(self) -> None:
        assert self._proc is not None
        assert self._proc.stdin is not None

        chunk_count = 0
        total_bytes = 0
        max_retries = 10
        retry_delay = 2.0

        logger.info(f"Capture feed loop started for {self.serial}")

        for attempt in range(max_retries):
            try:
                # セッションを毎回取得（再起動で別インスタンスになる可能性があるため）
                session = await self._stream_manager.get_or_create(self.serial)
                logger.info(f"Capture feed {self.serial}: subscribed to session (attempt {attempt + 1})")
                async for chunk in session.subscribe():
                    if not chunk or self._proc is None:
                        break
                    
                    # SPS変更を検出（解像度変更の検出）
                    sps = _find_sps_nal_unit(chunk)
                    if sps is not None:
                        if self._last_sps is None:
                            logger.info(f"Capture feed {self.serial}: initial SPS detected")
                            self._last_sps = sps
                        elif sps != self._last_sps:
                            logger.info(f"Capture feed {self.serial}: SPS changed (resolution change), restarting decoder")
                            self._last_sps = sps
                            # ffmpegプロセスを再起動
                            await self._restart_decoder_for_resolution_change(chunk)
                            continue
                    
                    try:
                        self._proc.stdin.write(chunk)
                        await self._proc.stdin.drain()
                        chunk_count += 1
                        total_bytes += len(chunk)
                        if chunk_count <= 3 or chunk_count % 100 == 0:
                            logger.info(f"Capture feed {self.serial}: chunk #{chunk_count}, size={len(chunk)}, total={total_bytes}")
                    except (BrokenPipeError, ConnectionResetError):
                        logger.warning(f"Capture feed {self.serial}: pipe broken after {chunk_count} chunks")
                        return
                # Normal exit from subscribe() iterator
                logger.info(f"Capture feed {self.serial}: subscribe iterator ended normally after {chunk_count} chunks")
                break
            except asyncio.CancelledError:
                raise
            except (ConnectionRefusedError, OSError) as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Capture feed {self.serial}: connection error ({e}), retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 5.0)
                else:
                    logger.error(f"Capture feed loop error for {self.serial}: {e} (giving up after {max_retries} attempts)")
            except Exception as e:
                logger.error(f"Capture feed loop error for {self.serial}: {e}")
                break

        logger.info(f"Capture feed loop ended for {self.serial}: {chunk_count} chunks, {total_bytes} bytes")

    async def _read_ffmpeg_stderr_loop(self) -> None:
        assert self._proc is not None
        assert self._proc.stderr is not None

        try:
            while True:
                line = await self._proc.stderr.readline()
                if not line:
                    break

                text = line.decode("utf-8", errors="ignore").rstrip()
                # Log all ffmpeg stderr for debugging
                logger.debug(f"ffmpeg stderr [{self.serial}]: {text}")
                
                # Detect resolution changes (not just initial detection)
                if "Video:" not in text:
                    continue
                m = _RE_DIM.search(text)
                if not m:
                    continue

                w = int(m.group("w"))
                h = int(m.group("h"))
                if w <= 0 or h <= 0:
                    continue

                if self._width != w or self._height != h:
                    old_w, old_h = self._width, self._height
                    self._width = w
                    self._height = h
                    if old_w is None:
                        logger.info(f"Capture decoder resolution for {self.serial}: {w}x{h}")
                    else:
                        logger.info(f"Capture decoder resolution changed for {self.serial}: {old_w}x{old_h} -> {w}x{h}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Capture stderr loop error for {self.serial}: {e}")

    async def _read_rawvideo_loop(self) -> None:
        assert self._proc is not None
        assert self._proc.stdout is not None

        buf = bytearray()
        read_count = 0
        total_bytes = 0
        frame_count = 0
        last_width: int | None = None
        last_height: int | None = None

        logger.info(f"Capture rawvideo loop started for {self.serial}")

        try:
            while True:
                chunk = await self._proc.stdout.read(256 * 1024)
                if not chunk:
                    logger.warning(f"Capture rawvideo loop {self.serial}: EOF after {read_count} reads, {total_bytes} bytes")
                    break

                read_count += 1
                total_bytes += len(chunk)
                buf.extend(chunk)

                if read_count <= 3 or read_count % 100 == 0:
                    logger.info(f"Capture rawvideo {self.serial}: read #{read_count}, chunk={len(chunk)}, total={total_bytes}, buf={len(buf)}, w={self._width}, h={self._height}")

                if self._width is None or self._height is None:
                    continue
                
                # 解像度変更時にバッファをクリア
                if self._resolution_changed:
                    logger.info(f"Capture rawvideo {self.serial}: resolution changed flag set, clearing buffer ({len(buf)} bytes)")
                    buf.clear()
                    self._resolution_changed = False
                elif last_width is not None and last_height is not None:
                    if self._width != last_width or self._height != last_height:
                        logger.info(f"Capture rawvideo {self.serial}: resolution changed, clearing buffer ({len(buf)} bytes)")
                        buf.clear()
                        
                last_width = self._width
                last_height = self._height
                
                frame_size = _yuv420p_frame_size(self._width, self._height)
                if frame_size <= 0:
                    continue

                # Consume complete frames; keep only latest.
                latest: bytes | None = None
                while len(buf) >= frame_size:
                    latest = bytes(buf[:frame_size])
                    del buf[:frame_size]
                    frame_count += 1

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
                
                if frame_count % 30 == 1:
                    logger.debug(f"Capture rawvideo {self.serial}: frame {frame_count} updated")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Capture rawvideo loop error for {self.serial}: {e}")
        finally:
            logger.info(f"Capture rawvideo loop ended for {self.serial}: {frame_count} frames")


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
