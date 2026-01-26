from __future__ import annotations

from app.services.capture_manager import _extract_complete_jpegs, _quality_percent_to_mjpeg_qscale


def test_extract_complete_jpegs_handles_split_markers() -> None:
    # Minimal fake JPEGs with SOI/EOI markers.
    jpeg1 = b"\xff\xd8" + b"aaa" + b"\xff\xd9"
    jpeg2 = b"\xff\xd8" + b"bbb" + b"\xff\xd9"

    buf = bytearray()

    # Feed in awkwardly split chunks.
    buf.extend(jpeg1[:3])
    assert _extract_complete_jpegs(buf) == []

    buf.extend(jpeg1[3:] + jpeg2[:2])
    frames = _extract_complete_jpegs(buf)
    assert frames == [jpeg1]

    buf.extend(jpeg2[2:])
    frames = _extract_complete_jpegs(buf)
    assert frames == [jpeg2]


def test_extract_complete_jpegs_ignores_leading_garbage() -> None:
    jpeg = b"\xff\xd8" + b"xyz" + b"\xff\xd9"

    buf = bytearray(b"garbage" + jpeg)
    frames = _extract_complete_jpegs(buf)

    assert frames == [jpeg]


def test_quality_percent_to_mjpeg_qscale_range() -> None:
    assert _quality_percent_to_mjpeg_qscale(1) == 31
    assert _quality_percent_to_mjpeg_qscale(100) == 2
