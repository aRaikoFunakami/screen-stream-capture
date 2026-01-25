"""
scrcpy-serverに直接接続してraw H.264ストリームを取得するクライアント

使用方法:
    client = ScrcpyRawClient("emulator-5554")
    await client.start()
    async for chunk in client.stream():
        # H.264データを処理
        pass
    await client.stop()
"""

import asyncio
import logging
import subprocess
import random
from typing import AsyncIterator, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ScrcpyConfig:
    """scrcpy-server設定"""
    max_size: int = 720
    max_fps: int = 15
    video_bit_rate: int = 2_000_000
    video_codec: str = "h264"  # h264, h265, av1


class ScrcpyRawClient:
    """scrcpy-serverに直接接続してraw H.264ストリームを取得"""
    
    SERVER_JAR_PATH = "/data/local/tmp/scrcpy-server.jar"
    SERVER_VERSION = "3.3.4"
    
    def __init__(
        self,
        device_serial: str,
        config: Optional[ScrcpyConfig] = None,
        local_port: int = 0,  # 0 = auto-assign
        server_jar_local: str = "",  # ローカルのjarファイルパス
    ):
        self.device_serial = device_serial
        self.config = config or ScrcpyConfig()
        self.local_port = local_port or self._find_free_port()
        self.server_jar_local = server_jar_local
        
        self._server_process: Optional[asyncio.subprocess.Process] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._running = False
    
    def _find_free_port(self) -> int:
        """空きポートを見つける"""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]
    
    async def _run_adb(self, *args: str) -> tuple[int, str, str]:
        """adbコマンドを実行"""
        cmd = ["adb", "-s", self.device_serial] + list(args)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode or 0, stdout.decode(), stderr.decode()
    
    async def _push_server(self) -> None:
        """サーバーjarをデバイスにプッシュ"""
        if not self.server_jar_local:
            logger.debug("No local server jar specified, skipping push")
            return
        
        logger.info(f"Pushing server jar to device: {self.server_jar_local}")
        code, stdout, stderr = await self._run_adb(
            "push", self.server_jar_local, self.SERVER_JAR_PATH
        )
        if code != 0:
            raise RuntimeError(f"Failed to push server: {stderr}")
        logger.debug(f"Push result: {stdout}")
    
    async def _setup_tunnel(self) -> None:
        """adb forwardを設定"""
        # 既存のフォワードを削除
        await self._run_adb("forward", "--remove-all")
        
        # 新しいフォワードを設定
        code, stdout, stderr = await self._run_adb(
            "forward", f"tcp:{self.local_port}", "localabstract:scrcpy"
        )
        if code != 0:
            raise RuntimeError(f"Failed to setup tunnel: {stderr}")
        logger.info(f"Tunnel established on port {self.local_port}")
    
    async def _start_server(self) -> None:
        """scrcpy-serverを起動"""
        cmd = [
            "adb", "-s", self.device_serial, "shell",
            f"CLASSPATH={self.SERVER_JAR_PATH}",
            "app_process", "/", "com.genymobile.scrcpy.Server",
            self.SERVER_VERSION,
            "tunnel_forward=true",
            "audio=false",
            "control=false",
            "cleanup=false",
            "raw_stream=true",
            f"max_size={self.config.max_size}",
            f"max_fps={self.config.max_fps}",
            f"video_bit_rate={self.config.video_bit_rate}",
        ]
        
        if self.config.video_codec != "h264":
            cmd.append(f"video_codec={self.config.video_codec}")
        
        logger.info(f"Starting scrcpy-server: {' '.join(cmd)}")
        
        self._server_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        
        # サーバーが起動するまで待機
        await asyncio.sleep(1.5)
        
        if self._server_process.returncode is not None:
            raise RuntimeError("Server process exited unexpectedly")
        
        logger.info("Server started successfully")
    
    async def _connect(self) -> None:
        """TCPソケットに接続"""
        logger.info(f"Connecting to localhost:{self.local_port}")
        
        for attempt in range(10):
            try:
                self._reader, self._writer = await asyncio.open_connection(
                    "localhost", self.local_port
                )
                logger.info("Connected to server")
                return
            except ConnectionRefusedError:
                if attempt < 9:
                    await asyncio.sleep(0.5)
                else:
                    raise
    
    async def start(self) -> None:
        """サーバーを起動し接続"""
        if self._running:
            raise RuntimeError("Client already running")
        
        try:
            await self._push_server()
            await self._setup_tunnel()
            await self._start_server()
            await self._connect()
            self._running = True
        except Exception:
            await self.stop()
            raise
    
    async def stream(self, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        """raw H.264/H.265チャンクを非同期で読み取り"""
        if not self._running or not self._reader:
            raise RuntimeError("Client not started")
        
        try:
            while self._running:
                chunk = await self._reader.read(chunk_size)
                if not chunk:
                    logger.info("Stream ended (server closed connection)")
                    break
                yield chunk
        except asyncio.CancelledError:
            logger.info("Stream cancelled")
            raise
        except Exception as e:
            logger.error(f"Stream error: {e}")
            raise
    
    async def stop(self) -> None:
        """クリーンアップ"""
        self._running = False
        
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None
        
        if self._server_process:
            self._server_process.terminate()
            try:
                await asyncio.wait_for(self._server_process.wait(), timeout=3)
            except asyncio.TimeoutError:
                self._server_process.kill()
            self._server_process = None
        
        # フォワードを削除
        await self._run_adb("forward", "--remove-all")
        
        logger.info("Client stopped")
    
    @property
    def is_running(self) -> bool:
        return self._running


async def main():
    """テスト用のメイン関数"""
    logging.basicConfig(level=logging.INFO)
    
    client = ScrcpyRawClient(
        "emulator-5554",
        config=ScrcpyConfig(max_size=720, max_fps=15),
    )
    
    try:
        await client.start()
        
        total_bytes = 0
        start_time = asyncio.get_event_loop().time()
        
        async for chunk in client.stream():
            total_bytes += len(chunk)
            elapsed = asyncio.get_event_loop().time() - start_time
            print(f"Received {len(chunk)} bytes, total: {total_bytes}, elapsed: {elapsed:.1f}s")
            
            if elapsed >= 5:
                break
        
        print(f"\nTotal: {total_bytes} bytes in {elapsed:.1f} seconds")
        print(f"Bitrate: {total_bytes * 8 / elapsed / 1000:.1f} kbps")
        
    finally:
        await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
