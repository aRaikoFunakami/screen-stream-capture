"""
ScrcpyClient - scrcpy-serverに直接接続してraw H.264ストリームを取得

低レベルクライアント。セッション管理が必要な場合は StreamSession を使用してください。
"""

import asyncio
import logging
import socket
from pathlib import Path
from typing import AsyncIterator, Optional

from .config import StreamConfig

logger = logging.getLogger(__name__)


class ScrcpyClient:
    """scrcpy-serverに直接接続してraw H.264ストリームを取得
    
    Examples:
        # コンテキストマネージャ使用（推奨）
        async with ScrcpyClient("emulator-5554", server_jar="path/to/jar") as client:
            async for chunk in client.stream():
                process(chunk)
        
        # 手動管理
        client = ScrcpyClient("emulator-5554", server_jar="path/to/jar")
        await client.start()
        try:
            async for chunk in client.stream():
                process(chunk)
        finally:
            await client.stop()
    """
    
    DEVICE_JAR_PATH = "/data/local/tmp/scrcpy-server.jar"
    SERVER_VERSION = "3.3.4"
    
    def __init__(
        self,
        serial: str,
        server_jar: str,
        config: Optional[StreamConfig] = None,
        local_port: int = 0,
    ):
        """
        Args:
            serial: Android デバイスのシリアル番号 (例: "emulator-5554")
            server_jar: ローカルの scrcpy-server.jar ファイルパス
            config: ストリーミング設定 (省略時はデフォルト)
            local_port: ローカルポート (0 = 自動割り当て)
        
        Raises:
            FileNotFoundError: server_jar が存在しない場合
        """
        self.serial = serial
        self.server_jar = Path(server_jar)
        self.config = config or StreamConfig()
        self.local_port = local_port or self._find_free_port()
        
        if not self.server_jar.exists():
            raise FileNotFoundError(f"Server jar not found: {self.server_jar}")
        
        self._server_process: Optional[asyncio.subprocess.Process] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._running = False
    
    @staticmethod
    def _find_free_port() -> int:
        """空きポートを見つける"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]
    
    async def _run_adb(self, *args: str) -> tuple[int, str, str]:
        """adbコマンドを実行"""
        cmd = ["adb", "-s", self.serial] + list(args)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode or 0, stdout.decode(), stderr.decode()
    
    async def _push_server(self) -> None:
        """サーバーjarをデバイスにプッシュ"""
        logger.info(f"Pushing server jar to device: {self.server_jar}")
        code, stdout, stderr = await self._run_adb(
            "push", str(self.server_jar), self.DEVICE_JAR_PATH
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
            "adb", "-s", self.serial, "shell",
            f"CLASSPATH={self.DEVICE_JAR_PATH}",
            "app_process", "/", "com.genymobile.scrcpy.Server",
            self.SERVER_VERSION,
            "tunnel_forward=true",
            "audio=false",
            "control=false",
            "cleanup=false",
            "raw_stream=true",
        ] + self.config.to_scrcpy_args()
        
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
        """サーバーを起動し接続
        
        Raises:
            RuntimeError: 既に起動中、またはサーバー起動に失敗した場合
        """
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
        """raw H.264/H.265チャンクを非同期で読み取り
        
        Args:
            chunk_size: 1回の読み取りサイズ (デフォルト: 64KB)
        
        Yields:
            bytes: H.264/H.265 データチャンク
        
        Raises:
            RuntimeError: クライアントが起動していない場合
        """
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
        """クライアントが起動中かどうか"""
        return self._running
    
    async def __aenter__(self) -> "ScrcpyClient":
        """コンテキストマネージャ開始"""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """コンテキストマネージャ終了"""
        await self.stop()
