"""Latency measurement endpoints.

遅延計測専用のエンドポイント。scrcpy や実データを使わず、純粋な遅延を測定する。

## A. WebSocket Echo (RTT)
GET /api/ws/latency/echo
- クライアントから送信したペイロードをそのまま返す
- RTT = 受信時刻 - 送信時刻（クライアント側で計測）
- サーバ処理時間もログに記録

## B. Synthetic Stream (Backend処理遅延)
GET /api/ws/latency/synthetic-stream
- 固定サイズの疑似NALを固定FPSで生成
- 生成→キュー→送信の遅延をサーバ側でログ
"""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/latency/echo")
async def websocket_echo(websocket: WebSocket) -> None:
    """WebSocket Echo - 純粋なネットワーク遅延測定用

    Protocol:
    - client -> server: binary (8 bytes seq + N bytes payload)
    - server -> client: 同じバイナリをそのまま返す

    クライアント側で送信時刻を記録し、受信時刻との差でRTTを算出。
    サーバ側では処理時間をログに記録。
    """
    await websocket.accept()

    logger.info("Echo WebSocket connected")
    echo_count = 0

    try:
        while True:
            data = await websocket.receive_bytes()
            recv_t = time.perf_counter()

            # エコー送信
            await websocket.send_bytes(data)
            send_t = time.perf_counter()

            echo_count += 1
            proc_ms = (send_t - recv_t) * 1000

            # 30回ごとにログ出力
            if echo_count % 30 == 0:
                # seq を解析（先頭8バイトがseq番号と仮定）
                seq = struct.unpack(">Q", data[:8])[0] if len(data) >= 8 else echo_count
                logger.info(
                    f"[ECHO] seq={seq} proc_ms={proc_ms:.3f} payload_bytes={len(data)} count={echo_count}"
                )

    except WebSocketDisconnect:
        logger.info(f"Echo WebSocket disconnected. total_echoes={echo_count}")
    except Exception as e:
        logger.error(f"Echo WebSocket error: {e}")


@router.websocket("/ws/latency/synthetic-stream")
async def websocket_synthetic_stream(
    websocket: WebSocket,
    fps: int = Query(default=30, ge=1, le=120),
    payload_size: int = Query(default=4096, ge=64, le=1048576),
    duration_sec: int = Query(default=10, ge=1, le=60),
) -> None:
    """Synthetic Stream - Backend処理遅延測定用

    固定サイズの疑似NALを固定FPSで生成し、送信する。
    scrcpy/エンコードを排除した純粋なバックエンド処理遅延を測定。

    Query params:
    - fps: 生成レート (default: 30)
    - payload_size: ペイロードサイズ (default: 4096)
    - duration_sec: 計測時間 (default: 10)

    Protocol:
    - server -> client: binary (8 bytes seq + 8 bytes gen_t + N bytes payload)

    サーバ側で生成→送信完了の遅延をログ。
    """
    await websocket.accept()

    logger.info(
        f"Synthetic stream started: fps={fps} payload_size={payload_size} duration_sec={duration_sec}"
    )

    interval = 1.0 / fps
    seq = 0
    total_bytes = 0
    start_time = time.perf_counter()
    end_time = start_time + duration_sec

    # 固定ペイロード（ゼロ埋め）
    payload_body = bytes(payload_size - 16)  # 16 = seq(8) + gen_t(8)

    try:
        while time.perf_counter() < end_time:
            gen_t = time.perf_counter()
            seq += 1

            # ペイロード構築: seq(8) + gen_t(8) + body
            header = struct.pack(">Qd", seq, gen_t)
            data = header + payload_body

            await websocket.send_bytes(data)
            send_done_t = time.perf_counter()

            total_bytes += len(data)
            send_ms = (send_done_t - gen_t) * 1000

            # 30回ごとにログ出力
            if seq % 30 == 0:
                logger.info(
                    f"[SYNTH] seq={seq} send_ms={send_ms:.3f} payload_bytes={len(data)}"
                )

            # 次フレームまで待機
            elapsed = time.perf_counter() - gen_t
            sleep_time = interval - elapsed
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

        # 完了通知（空バイトで終了シグナル）
        await websocket.send_bytes(b"")
        await websocket.close()

        elapsed_total = time.perf_counter() - start_time
        actual_fps = seq / elapsed_total if elapsed_total > 0 else 0
        logger.info(
            f"Synthetic stream completed: frames={seq} elapsed={elapsed_total:.2f}s "
            f"actual_fps={actual_fps:.1f} total_bytes={total_bytes}"
        )

    except WebSocketDisconnect:
        logger.info(f"Synthetic stream disconnected. frames={seq}")
    except Exception as e:
        logger.error(f"Synthetic stream error: {e}")
