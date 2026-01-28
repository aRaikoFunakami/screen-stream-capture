import asyncio
from datetime import datetime, timezone

import pytest

from app.services.capture_manager import CaptureWorker, FrameBuffer


@pytest.mark.asyncio
async def test_get_latest_frame_default_returns_immediately_when_available() -> None:
    worker = CaptureWorker("dummy", stream_manager=object(), output_dir="/tmp")

    fb = FrameBuffer(
        width=10,
        height=10,
        pix_fmt="yuv420p",
        captured_at=datetime.now(timezone.utc).isoformat(),
        data=b"x" * 150,
    )

    async with worker._cond:
        worker._latest_frame = fb
        worker._seq = 123
        worker._cond.notify_all()

    # Should not wait.
    got = await asyncio.wait_for(
        worker._get_latest_frame(timeout_sec=0.01, wait_for_new_frame=False),
        timeout=0.2,
    )
    assert got is fb


@pytest.mark.asyncio
async def test_get_latest_frame_wait_for_new_frame_falls_back_on_timeout() -> None:
    worker = CaptureWorker("dummy", stream_manager=object(), output_dir="/tmp")

    fb = FrameBuffer(
        width=10,
        height=10,
        pix_fmt="yuv420p",
        captured_at=datetime.now(timezone.utc).isoformat(),
        data=b"x" * 150,
    )

    async with worker._cond:
        worker._latest_frame = fb
        worker._seq = 1
        worker._cond.notify_all()

    # No new frame will arrive, so it should time out and return existing frame.
    got = await worker._get_latest_frame(timeout_sec=0.01, wait_for_new_frame=True)
    assert got is fb


@pytest.mark.asyncio
async def test_get_latest_frame_waits_for_first_frame_when_none_available() -> None:
    worker = CaptureWorker("dummy", stream_manager=object(), output_dir="/tmp")

    fb = FrameBuffer(
        width=10,
        height=10,
        pix_fmt="yuv420p",
        captured_at=datetime.now(timezone.utc).isoformat(),
        data=b"x" * 150,
    )

    async def publish_first_frame() -> None:
        await asyncio.sleep(0.01)
        async with worker._cond:
            worker._latest_frame = fb
            worker._seq += 1
            worker._cond.notify_all()

    pub_task = asyncio.create_task(publish_first_frame())
    try:
        got = await worker._get_latest_frame(timeout_sec=0.2, wait_for_new_frame=False)
        assert got is fb
    finally:
        pub_task.cancel()
