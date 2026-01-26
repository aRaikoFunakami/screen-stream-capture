from __future__ import annotations

from app.services.capture_manager import _quality_percent_to_mjpeg_qscale, _yuv420p_frame_size


def test_quality_percent_to_mjpeg_qscale_range() -> None:
    assert _quality_percent_to_mjpeg_qscale(1) == 31
    assert _quality_percent_to_mjpeg_qscale(100) == 2


def test_yuv420p_frame_size() -> None:
    # 2x2 yuv420p = 2*2 (Y) + 1*1 (U) + 1*1 (V) = 6 bytes
    assert _yuv420p_frame_size(2, 2) == 6
