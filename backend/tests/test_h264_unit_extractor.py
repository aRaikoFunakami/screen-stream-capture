from __future__ import annotations

from android_screen_stream.session import _H264UnitExtractor


def test_h264_unit_extractor_annexb_extracts_complete_nals() -> None:
    ex = _H264UnitExtractor()

    sps = b"\x00\x00\x00\x01" + bytes([0x67, 0x01, 0x02])
    idr = b"\x00\x00\x00\x01" + bytes([0x65, 0x03, 0x04])
    non_idr = b"\x00\x00\x00\x01" + bytes([0x61, 0x05])

    out = ex.push(sps + idr + non_idr)

    # Annex-B extractor keeps the last NAL in buffer until it sees the next start code.
    assert out == [sps, idr]


def test_h264_unit_extractor_avcc_converts_to_annexb() -> None:
    ex = _H264UnitExtractor()

    sps_payload = bytes([0x67, 0x11, 0x22, 0x33])
    idr_payload = bytes([0x65, 0x44, 0x55])

    avcc = (
        len(sps_payload).to_bytes(4, "big")
        + sps_payload
        + len(idr_payload).to_bytes(4, "big")
        + idr_payload
    )

    # Feed in two chunks to ensure buffering works.
    out1 = ex.push(avcc[:5])
    out2 = ex.push(avcc[5:])

    assert out1 == []
    assert out2 == [b"\x00\x00\x00\x01" + sps_payload, b"\x00\x00\x00\x01" + idr_payload]


def test_h264_unit_extractor_skips_leading_garbage_for_avcc() -> None:
    ex = _H264UnitExtractor()

    garbage = b"X" * 9
    sps_payload = bytes([0x67, 0xAA])
    avcc = len(sps_payload).to_bytes(4, "big") + sps_payload

    out = ex.push(garbage + avcc)

    assert out == [b"\x00\x00\x00\x01" + sps_payload]


def test_h264_unit_extractor_skips_leading_garbage_for_annexb() -> None:
    ex = _H264UnitExtractor()

    garbage = b"X" * 9
    nal1 = b"\x00\x00\x00\x01" + bytes([0x67, 0x01])
    nal2 = b"\x00\x00\x00\x01" + bytes([0x65, 0x02])
    nal3 = b"\x00\x00\x00\x01" + bytes([0x61, 0x03])

    out = ex.push(garbage + nal1 + nal2 + nal3)

    assert out == [nal1, nal2]
