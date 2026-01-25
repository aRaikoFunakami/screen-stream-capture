import asyncio

import pytest

from android_screen_stream.session import StreamSession


def _nal(nal_type: int, payload: bytes = b"\x00") -> bytes:
    # forbidden_zero_bit=0, nal_ref_idc=3 (0b11) にしておく
    header = bytes([(3 << 5) | (nal_type & 0x1F)])
    return b"\x00\x00\x00\x01" + header + payload


def _nal_type(nal: bytes) -> int:
    assert nal.startswith(b"\x00\x00\x00\x01")
    return nal[4] & 0x1F


class _DummyClient:
    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks

    async def stream(self):
        for c in self._chunks:
            await asyncio.sleep(0)
            yield c

    async def stop(self) -> None:
        return


@pytest.mark.asyncio
async def test_late_joiner_receives_sps_pps_idr_first() -> None:
    # Stream: SPS, PPS, AUD, IDR, P, P, P...
    stream = b"".join(
        [
            _nal(7, b"S"),  # SPS
            _nal(8, b"P"),  # PPS
            _nal(9, b"A"),  # AUD
            _nal(5, b"I"),  # IDR
            _nal(1, b"1"),
            _nal(1, b"2"),
            _nal(1, b"3"),
        ]
    )

    # 任意分割（NAL境界を跨ぐ）
    chunks = [stream[:7], stream[7:19], stream[19:33], stream[33:49], stream[49:]]

    session = StreamSession(serial="dummy", server_jar="dummy")
    session._client = _DummyClient(chunks)  # type: ignore[attr-defined]
    session._running = True  # type: ignore[attr-defined]

    broadcast_task = asyncio.create_task(session._run_broadcast())  # type: ignore[attr-defined]
    session._broadcast_task = broadcast_task  # type: ignore[attr-defined]

    # 先行視聴者
    gen1 = session.subscribe()
    # IDR が観測されるまで消費して GOP キャッシュを確実に構築
    saw_idr = False
    for _ in range(20):
        nal = await asyncio.wait_for(anext(gen1), timeout=1)
        if _nal_type(nal) == 5:
            saw_idr = True
            break
    assert saw_idr

    # late join
    gen2 = session.subscribe()

    # late joiner の最初は必ず SPS/PPS/IDR が先頭に来る（AUD/SEI は間に挟まってOK）
    first_nals = [await asyncio.wait_for(anext(gen2), timeout=1) for _ in range(6)]
    types = [_nal_type(x) for x in first_nals]

    # SPS, PPS が先頭2つ
    assert types[0] == 7
    assert types[1] == 8

    # IDR が早期に出現し、IDR より前に P(=1) が出ない
    assert 5 in types
    idr_idx = types.index(5)
    assert 1 not in types[:idr_idx]

    await gen1.aclose()
    await gen2.aclose()
    await session.stop()
