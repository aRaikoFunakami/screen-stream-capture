#!/usr/bin/env python3
"""
クライアント側の遅延計測スクリプト

A. WebSocket Echo RTT計測
B. Synthetic Stream 受信計測
C. scrcpy ストリーム遅延計測
"""

import argparse
import asyncio
import json
import struct
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import websockets
except ImportError:
    print("websockets パッケージが必要です: pip install websockets")
    sys.exit(1)


@dataclass
class Stats:
    """統計情報"""
    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0
    samples: list[float] = field(default_factory=list)

    def add(self, ms: float) -> None:
        self.count += 1
        self.total_ms += ms
        self.min_ms = min(self.min_ms, ms)
        self.max_ms = max(self.max_ms, ms)
        self.samples.append(ms)

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count > 0 else 0.0

    def percentile(self, p: float) -> float:
        if not self.samples:
            return 0.0
        sorted_samples = sorted(self.samples)
        idx = int(len(sorted_samples) * p / 100)
        return sorted_samples[min(idx, len(sorted_samples) - 1)]

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "avg_ms": round(self.avg_ms, 3),
            "min_ms": round(self.min_ms, 3) if self.min_ms != float("inf") else 0,
            "max_ms": round(self.max_ms, 3),
            "p50_ms": round(self.percentile(50), 3),
            "p95_ms": round(self.percentile(95), 3),
            "p99_ms": round(self.percentile(99), 3),
        }


async def measure_echo_rtt(
    url: str,
    count: int = 100,
    payload_size: int = 1024,
    interval_ms: int = 33,
) -> Stats:
    """A. WebSocket Echo RTT計測

    Args:
        url: WebSocket URL (例: ws://localhost:8000/api/ws/latency/echo)
        count: 送信回数
        payload_size: ペイロードサイズ
        interval_ms: 送信間隔 (ms)
    """
    stats = Stats()
    payload_body = bytes(payload_size - 8)  # 8 = seq

    print(f"Echo RTT計測: url={url} count={count} payload={payload_size}bytes")

    async with websockets.connect(url) as ws:
        for seq in range(1, count + 1):
            # ペイロード構築: seq(8) + body
            header = struct.pack(">Q", seq)
            data = header + payload_body

            send_t = time.perf_counter()
            await ws.send(data)
            response = await ws.recv()
            recv_t = time.perf_counter()

            rtt_ms = (recv_t - send_t) * 1000
            stats.add(rtt_ms)

            if seq % 10 == 0:
                print(f"  seq={seq} rtt={rtt_ms:.2f}ms")

            await asyncio.sleep(interval_ms / 1000)

    return stats


async def measure_synthetic_stream(
    url: str,
    fps: int = 30,
    payload_size: int = 4096,
    duration_sec: int = 10,
) -> Stats:
    """B. Synthetic Stream 受信計測

    サーバが生成した疑似NALの受信遅延を計測。
    ペイロード内の gen_t と受信時刻の差を測定。

    ※注意: サーバ/クライアントの時刻は同期されていないため、
    ここでは「受信間隔のばらつき」を見る。
    """
    stats = Stats()
    url_with_params = f"{url}?fps={fps}&payload_size={payload_size}&duration_sec={duration_sec}"

    print(f"Synthetic Stream計測: url={url_with_params}")

    prev_recv_t: Optional[float] = None
    frame_count = 0
    expected_interval_ms = 1000.0 / fps

    async with websockets.connect(url_with_params) as ws:
        async for message in ws:
            if isinstance(message, bytes):
                if len(message) == 0:
                    # 終了シグナル
                    break

                recv_t = time.perf_counter()
                frame_count += 1

                if prev_recv_t is not None:
                    interval_ms = (recv_t - prev_recv_t) * 1000
                    jitter_ms = abs(interval_ms - expected_interval_ms)
                    stats.add(jitter_ms)

                    if frame_count % 30 == 0:
                        print(f"  frame={frame_count} interval={interval_ms:.2f}ms jitter={jitter_ms:.2f}ms")

                prev_recv_t = recv_t

    print(f"受信完了: frames={frame_count}")
    return stats


async def measure_scrcpy_stream(
    url: str,
    duration_sec: int = 10,
) -> tuple[Stats, Stats]:
    """C. scrcpy ストリーム計測

    実際のH.264ストリームの受信間隔と受信サイズを計測。

    Returns:
        (interval_stats, size_stats)
    """
    interval_stats = Stats()
    size_stats = Stats()

    print(f"scrcpy Stream計測: url={url} duration={duration_sec}s")

    prev_recv_t: Optional[float] = None
    frame_count = 0
    total_bytes = 0
    start_time = time.perf_counter()

    try:
        async with websockets.connect(url) as ws:
            while time.perf_counter() - start_time < duration_sec:
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=5.0)
                except asyncio.TimeoutError:
                    print("  タイムアウト - デバイスからデータが来ていません")
                    break

                if isinstance(message, bytes):
                    recv_t = time.perf_counter()
                    frame_count += 1
                    total_bytes += len(message)
                    size_stats.add(len(message))

                    if prev_recv_t is not None:
                        interval_ms = (recv_t - prev_recv_t) * 1000
                        interval_stats.add(interval_ms)

                    if frame_count % 30 == 0:
                        elapsed = time.perf_counter() - start_time
                        print(f"  frames={frame_count} elapsed={elapsed:.1f}s total={total_bytes/1024:.1f}KB")

                    prev_recv_t = recv_t

    except Exception as e:
        print(f"接続エラー: {e}")

    print(f"受信完了: frames={frame_count} total={total_bytes/1024:.1f}KB")
    return interval_stats, size_stats


async def main():
    parser = argparse.ArgumentParser(description="遅延計測クライアント")
    parser.add_argument(
        "mode",
        choices=["echo", "synthetic", "scrcpy", "all"],
        help="計測モード",
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="サーバホスト (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="サーバポート (default: 8000)",
    )
    parser.add_argument(
        "--serial",
        default="emulator-5554",
        help="デバイスシリアル (scrcpyモード用)",
    )
    parser.add_argument(
        "--output",
        help="結果出力ファイル (JSON)",
    )

    args = parser.parse_args()
    base_url = f"ws://{args.host}:{args.port}"

    results = {}

    if args.mode in ("echo", "all"):
        print("\n" + "=" * 60)
        print("A. WebSocket Echo RTT計測")
        print("=" * 60)
        stats = await measure_echo_rtt(f"{base_url}/api/ws/latency/echo")
        results["echo_rtt"] = stats.to_dict()
        print(f"結果: {json.dumps(results['echo_rtt'], indent=2)}")

    if args.mode in ("synthetic", "all"):
        print("\n" + "=" * 60)
        print("B. Synthetic Stream計測")
        print("=" * 60)
        stats = await measure_synthetic_stream(
            f"{base_url}/api/ws/latency/synthetic-stream"
        )
        results["synthetic_jitter"] = stats.to_dict()
        print(f"結果: {json.dumps(results['synthetic_jitter'], indent=2)}")

    if args.mode in ("scrcpy", "all"):
        print("\n" + "=" * 60)
        print("C. scrcpy Stream計測")
        print("=" * 60)
        interval_stats, size_stats = await measure_scrcpy_stream(
            f"{base_url}/api/ws/stream/{args.serial}"
        )
        results["scrcpy_interval"] = interval_stats.to_dict()
        results["scrcpy_size"] = size_stats.to_dict()
        print(f"受信間隔: {json.dumps(results['scrcpy_interval'], indent=2)}")
        print(f"フレームサイズ: {json.dumps(results['scrcpy_size'], indent=2)}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n結果を {args.output} に保存しました")

    return results


if __name__ == "__main__":
    asyncio.run(main())
