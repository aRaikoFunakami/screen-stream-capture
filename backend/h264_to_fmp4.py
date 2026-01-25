"""
H.264ストリームをfMP4に変換するパイプライン

scrcpy-server → raw H.264 → FFmpeg → fMP4 (fragmented MP4)
"""

import asyncio
import logging
from typing import AsyncIterator, Optional

logger = logging.getLogger(__name__)


class H264ToFmp4Converter:
    """H.264ストリームをfMP4に変換するFFmpegパイプライン"""
    
    def __init__(self):
        self._process: Optional[asyncio.subprocess.Process] = None
        self._running = False
        self._write_task: Optional[asyncio.Task] = None
    
    async def start(self, h264_stream: AsyncIterator[bytes]) -> None:
        """FFmpegプロセスを開始"""
        if self._running:
            raise RuntimeError("Converter already running")
        
        # FFmpegコマンド: H.264入力 → fMP4出力
        # 注意: fMP4はキーフレームごとにフラグメントを作成するため、
        # キーフレーム間隔（通常1-2秒）に依存する
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "warning",
            # 入力設定
            "-f", "h264",
            "-probesize", "32",  # 高速なストリーム開始のため小さく
            "-fflags", "+nobuffer+flush_packets",
            "-flags", "+low_delay",
            "-i", "pipe:0",
            # 出力設定
            "-c:v", "copy",  # 再エンコードなし
            "-f", "mp4",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "pipe:1",
        ]
        
        logger.info(f"Starting FFmpeg: {' '.join(cmd)}")
        
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        self._running = True
        
        # 入力ストリームをFFmpegに書き込むタスクを開始
        self._write_task = asyncio.create_task(
            self._write_input(h264_stream)
        )
        
        # stderrを監視するタスク
        asyncio.create_task(self._monitor_stderr())
        
        logger.info("FFmpeg converter started")
    
    async def _write_input(self, h264_stream: AsyncIterator[bytes]) -> None:
        """H.264ストリームをFFmpegのstdinに書き込み"""
        try:
            async for chunk in h264_stream:
                if not self._running or not self._process or not self._process.stdin:
                    break
                self._process.stdin.write(chunk)
                await self._process.stdin.drain()
        except Exception as e:
            logger.error(f"Error writing to FFmpeg: {e}")
        finally:
            if self._process and self._process.stdin:
                self._process.stdin.close()
                try:
                    await self._process.stdin.wait_closed()
                except Exception:
                    pass
    
    async def _monitor_stderr(self) -> None:
        """FFmpegのstderrを監視"""
        if not self._process or not self._process.stderr:
            return
        
        try:
            while self._running:
                line = await self._process.stderr.readline()
                if not line:
                    break
                logger.warning(f"FFmpeg: {line.decode().strip()}")
        except Exception:
            pass
    
    async def read_stream(self) -> AsyncIterator[bytes]:
        """fMP4ストリームを読み取り"""
        if not self._process or not self._process.stdout:
            raise RuntimeError("Converter not started")
        
        try:
            while self._running:
                chunk = await self._process.stdout.read(65536)
                if not chunk:
                    logger.info("FFmpeg output stream ended")
                    break
                yield chunk
        except asyncio.CancelledError:
            logger.info("Stream read cancelled")
            raise
        except Exception as e:
            logger.error(f"Error reading from FFmpeg: {e}")
            raise
    
    async def stop(self) -> None:
        """FFmpegプロセスを停止"""
        self._running = False
        
        if self._write_task:
            self._write_task.cancel()
            try:
                await self._write_task
            except asyncio.CancelledError:
                pass
        
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=3)
            except asyncio.TimeoutError:
                self._process.kill()
            self._process = None
        
        logger.info("FFmpeg converter stopped")
    
    @property
    def is_running(self) -> bool:
        return self._running


async def main():
    """テスト用のメイン関数"""
    from scrcpy_client import ScrcpyRawClient, ScrcpyConfig
    
    logging.basicConfig(level=logging.INFO)
    
    client = ScrcpyRawClient(
        "emulator-5554",
        config=ScrcpyConfig(max_size=720, max_fps=15),
    )
    converter = H264ToFmp4Converter()
    
    try:
        await client.start()
        await converter.start(client.stream())
        
        total_bytes = 0
        start_time = asyncio.get_event_loop().time()
        
        # 最初のfMP4データを保存
        output_data = b""
        
        async for chunk in converter.read_stream():
            total_bytes += len(chunk)
            output_data += chunk
            elapsed = asyncio.get_event_loop().time() - start_time
            print(f"fMP4: {len(chunk)} bytes, total: {total_bytes}, elapsed: {elapsed:.1f}s")
            
            if elapsed >= 5:
                break
        
        print(f"\nTotal fMP4: {total_bytes} bytes in {elapsed:.1f} seconds")
        
        # ファイルに保存してffprobeで確認
        with open("/tmp/test_output.mp4", "wb") as f:
            f.write(output_data)
        print("Saved to /tmp/test_output.mp4")
        
    finally:
        await converter.stop()
        await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
