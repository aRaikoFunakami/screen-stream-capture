#!/usr/bin/env python3
"""
H.264ストリームをfMP4に変換（frag_every_frame使用）
"""

import asyncio
import logging
from scrcpy_client import ScrcpyRawClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    # FFmpegプロセスを起動
    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "warning",
        "-f", "h264",
        "-probesize", "32",  # 最小限のプローブ
        "-analyzeduration", "0",
        "-fflags", "+nobuffer+flush_packets",
        "-flags", "+low_delay",
        "-i", "pipe:0",
        "-c:v", "copy",
        "-f", "mp4",
        "-movflags", "frag_every_frame+empty_moov+default_base_moof+omit_tfhd_offset",
        "-frag_duration", "0",  # 即座に出力
        "pipe:1",
    ]
    
    logger.info(f"Starting FFmpeg: {' '.join(ffmpeg_cmd)}")
    
    ffmpeg_proc = await asyncio.create_subprocess_exec(
        *ffmpeg_cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    
    # scrcpyクライアントを起動
    client = ScrcpyRawClient(device_serial="emulator-5554")
    await client.start()
    logger.info("scrcpy client started")
    
    # 結果を収集
    output_data = []
    start_time = asyncio.get_event_loop().time()
    
    async def read_ffmpeg_output():
        """FFmpegの出力を読み取る"""
        total = 0
        while True:
            chunk = await ffmpeg_proc.stdout.read(4096)
            if not chunk:
                break
            total += len(chunk)
            elapsed = asyncio.get_event_loop().time() - start_time
            logger.info(f"fMP4 output: {len(chunk)} bytes, total: {total}, elapsed: {elapsed:.1f}s")
            output_data.append(chunk)
            if total > 200000 or elapsed > 15:  # 200KB or 15秒で終了
                break
        return total
    
    async def feed_h264():
        """H.264データをFFmpegに送る"""
        total = 0
        async for chunk in client.stream():
            if ffmpeg_proc.stdin.is_closing():
                break
            ffmpeg_proc.stdin.write(chunk)
            await ffmpeg_proc.stdin.drain()
            total += len(chunk)
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > 15:  # 15秒で終了
                break
        return total
    
    # 並行して実行
    try:
        results = await asyncio.wait_for(
            asyncio.gather(read_ffmpeg_output(), feed_h264()),
            timeout=20
        )
        logger.info(f"Results - fMP4 output: {results[0]} bytes, H.264 input: {results[1]} bytes")
    except asyncio.TimeoutError:
        logger.warning("Timeout!")
    finally:
        # クリーンアップ
        await client.stop()
        ffmpeg_proc.stdin.close()
        await ffmpeg_proc.wait()
    
    # 結果をファイルに保存
    if output_data:
        with open("/tmp/test_frag_every_frame.mp4", "wb") as f:
            for chunk in output_data:
                f.write(chunk)
        logger.info("Saved to /tmp/test_frag_every_frame.mp4")


if __name__ == "__main__":
    asyncio.run(main())
