"""
StreamSession - マルチキャスト対応のストリーミングセッション管理

複数クライアントへの同時配信、設定の動的変更をサポート
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from .config import StreamConfig
from .client import ScrcpyClient

logger = logging.getLogger(__name__)


class _H264UnitExtractor:
    """H.264 の NAL unit を抽出する。

    上流(scrcpy)は端末/設定により、以下のどちらかのフォーマットで出てくることがある:

    - Annex-B: start code (00 00 01 / 00 00 00 01) 区切り
    - AVCC: 4byte big-endian length prefix 区切り

    いずれの場合も、返却する NAL は Annex-B (00 00 00 01) 形式に正規化する。
    末尾の未確定データは内部バッファに保持され、次回入力で確定する。
    """

    def __init__(
        self,
        *,
        max_buffer_bytes: int = 512 * 1024,
        max_nal_bytes: int = 4 * 1024 * 1024,
        scan_limit_bytes: int = 64,
    ):
        self._buf = bytearray()
        self._max = max_buffer_bytes
        self._max_nal = max_nal_bytes
        self._scan_limit = scan_limit_bytes

    @staticmethod
    def _starts_with_start_code(buf: bytearray) -> bool:
        return buf.startswith(b"\x00\x00\x01") or buf.startswith(b"\x00\x00\x00\x01")

    def _find_start_code(self, buf: bytearray) -> int:
        n = len(buf)
        i = 0
        while i < n - 3:
            if buf[i] == 0 and buf[i + 1] == 0:
                if buf[i + 2] == 1:
                    return i
                if i < n - 4 and buf[i + 2] == 0 and buf[i + 3] == 1:
                    return i
            i += 1
        return -1

    def _looks_like_avcc_at(self, buf: bytearray, offset: int) -> bool:
        if offset + 5 > len(buf):
            return False
        nal_len = int.from_bytes(buf[offset : offset + 4], "big")
        if nal_len <= 0 or nal_len > self._max_nal:
            return False
        if offset + 4 + nal_len > len(buf):
            return False
        nal_header = buf[offset + 4]
        nal_type = nal_header & 0x1F
        # 0 は reserved (invalid)。それ以外は型としてはあり得る。
        return nal_type != 0

    def _align_buffer(self) -> None:
        """バッファ先頭を Annex-B か AVCC に揃える（scrcpyの先頭ヘッダ等を捨てる）。"""
        buf = self._buf
        if not buf:
            return

        if self._starts_with_start_code(buf):
            return

        start_idx = self._find_start_code(buf)
        if start_idx > 0:
            del buf[:start_idx]
            return

        # Annex-B start code が見つからない場合、AVCCの長さプレフィックスっぽい位置を探す
        scan_to = min(self._scan_limit, max(0, len(buf) - 4))
        for i in range(scan_to + 1):
            if self._looks_like_avcc_at(buf, i):
                if i > 0:
                    del buf[:i]
                return

    def _extract_annexb(self) -> list[bytes]:
        buf = self._buf
        n = len(buf)
        if n < 4:
            return []

        starts: list[int] = []
        i = 0
        while i < n - 3:
            if buf[i] == 0 and buf[i + 1] == 0:
                if buf[i + 2] == 1:
                    starts.append(i)
                    i += 3
                    continue
                if i < n - 4 and buf[i + 2] == 0 and buf[i + 3] == 1:
                    starts.append(i)
                    i += 4
                    continue
            i += 1

        if not starts:
            return []

        # start code 前のゴミを捨てる
        if starts[0] != 0:
            del buf[: starts[0]]
            return self._extract_annexb()

        if len(starts) < 2:
            return []

        out: list[bytes] = []
        for a, b in zip(starts, starts[1:]):
            if a < b:
                out.append(bytes(buf[a:b]))

        # 末尾（最後の start code から）は未確定として保持
        last = starts[-1]
        self._buf = buf[last:]
        return out

    def _extract_avcc(self) -> list[bytes]:
        buf = self._buf
        out: list[bytes] = []

        # length-prefix で区切られた NAL を Annex-B に変換
        while True:
            if len(buf) < 4:
                break
            nal_len = int.from_bytes(buf[0:4], "big")
            if nal_len <= 0 or nal_len > self._max_nal:
                # ずれている可能性があるので、1byte進めて再アラインを試す
                del buf[:1]
                self._align_buffer()
                if not buf or self._starts_with_start_code(buf):
                    break
                continue
            if len(buf) < 4 + nal_len:
                break
            nal_payload = bytes(buf[4 : 4 + nal_len])
            out.append(b"\x00\x00\x00\x01" + nal_payload)
            del buf[: 4 + nal_len]
        return out

    def push(self, data: bytes) -> list[bytes]:
        if data:
            self._buf.extend(data)
            if len(self._buf) > self._max:
                cut = len(self._buf) - self._max
                del self._buf[:cut]

        self._align_buffer()
        if not self._buf:
            return []
        if self._starts_with_start_code(self._buf):
            return self._extract_annexb()
        return self._extract_avcc()


def _nal_type(nal: bytes) -> Optional[int]:
    if len(nal) < 5:
        return None
    if nal.startswith(b"\x00\x00\x00\x01"):
        return nal[4] & 0x1F
    if nal.startswith(b"\x00\x00\x01"):
        return nal[3] & 0x1F
    return None


@dataclass
class StreamStats:
    """ストリーム統計情報"""
    bytes_sent: int = 0
    chunks_sent: int = 0
    subscriber_count: int = 0


class StreamSession:
    """デバイスごとのストリーミングセッション
    
    scrcpy-serverに接続し、raw H.264データを複数クライアントにブロードキャスト
    
    Examples:
        session = StreamSession("emulator-5554", server_jar="path/to/jar")
        await session.start()
        
        # 購読
        async for chunk in session.subscribe():
            await websocket.send_bytes(chunk)
        
        # 設定変更（セッション再起動）
        await session.update_config(StreamConfig.high_quality())
        
        # 停止
        await session.stop()
    """
    
    def __init__(
        self,
        serial: str,
        server_jar: str,
        config: Optional[StreamConfig] = None,
    ):
        """
        Args:
            serial: Android デバイスのシリアル番号
            server_jar: ローカルの scrcpy-server.jar ファイルパス
            config: ストリーミング設定 (省略時はデフォルト)
        """
        self.serial = serial
        self.server_jar = server_jar
        self.config = config or StreamConfig()
        
        self._client: Optional[ScrcpyClient] = None
        self._running = False
        self._subscribers: list[asyncio.Queue[bytes]] = []
        self._lock = asyncio.Lock()
        self._subscribe_lock = asyncio.Lock()
        self._broadcast_task: Optional[asyncio.Task] = None
        self._delayed_stop_task: Optional[asyncio.Task] = None
        self._stats = StreamStats()

        # late joiner 対応: SPS/PPS と「最新GOP(IDR〜現在)」を保持して join 時に先に送る
        self._extractor = _H264UnitExtractor()
        self._last_sps: bytes = b""
        self._last_pps: bytes = b""
        self._au_prefix: list[bytes] = []  # AUD/SEI 等（直近VCL前）
        self._gop_nals: list[bytes] = []
        self._gop_bytes: int = 0
        self._gop_has_idr: bool = False
        self._gop_max_bytes: int = 4 * 1024 * 1024
    
    async def start(self) -> None:
        """ストリーミングセッションを開始"""
        if self._running:
            return
        
        logger.info(f"Starting stream session for {self.serial}")
        
        self._client = ScrcpyClient(
            serial=self.serial,
            server_jar=self.server_jar,
            config=self.config,
        )
        await self._client.start()
        
        self._running = True
        self._broadcast_task = asyncio.create_task(self._run_broadcast())
        
        logger.info(f"Stream session started for {self.serial}")
    
    async def stop(self) -> None:
        """ストリーミングセッションを停止"""
        if not self._running:
            return
        
        logger.info(f"Stopping stream session for {self.serial}")
        self._running = False
        
        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass

        if self._delayed_stop_task:
            self._delayed_stop_task.cancel()
            try:
                await self._delayed_stop_task
            except asyncio.CancelledError:
                pass
            self._delayed_stop_task = None
        
        if self._client:
            await self._client.stop()
            self._client = None

        # 解析/キャッシュをリセット
        self._extractor = _H264UnitExtractor()
        self._last_sps = b""
        self._last_pps = b""
        self._au_prefix.clear()
        self._gop_nals.clear()
        self._gop_bytes = 0
        self._gop_has_idr = False
        
        # 購読者に終了を通知
        async with self._lock:
            for queue in self._subscribers:
                try:
                    queue.put_nowait(b"")
                except asyncio.QueueFull:
                    pass
            self._subscribers.clear()
            self._stats.subscriber_count = 0
        
        logger.info(f"Stream session stopped for {self.serial}")
    
    async def update_config(self, config: StreamConfig) -> None:
        """設定を更新してセッションを再起動
        
        Args:
            config: 新しいストリーミング設定
        """
        logger.info(f"Updating config for {self.serial}: {config}")
        self.config = config
        
        if self._running:
            await self.stop()
            await self.start()
    
    async def subscribe(self) -> AsyncIterator[bytes]:
        """ストリームを購読

        ブラウザ側(JMuxer)は raw H.264 を受けて fMP4 を生成するため、途中参加(late join)
        では SPS/PPS + IDR が揃わず白画面になることがある。

        そのため、サーバ側で直近の SPS/PPS と「最新GOP(IDR〜現在)」を保持し、
        新規参加時に必ず "初期化できる塊" (SPS + PPS + IDR + 以降のフレーム) を先に送る。
        
        Yields:
            bytes: H.264 データチャンク
        """
        # 複数クライアントが同時に接続する場合に、0→1 判定〜起動/再起動が競合しないよう直列化
        async with self._subscribe_lock:
            # 遅延停止が予約されている場合はキャンセル（再接続のため）
            if self._delayed_stop_task:
                self._delayed_stop_task.cancel()
                self._delayed_stop_task = None

            # アーキテクチャ上、ブラウザ側(JMuxer)は raw H.264 を受けて fMP4 を生成するため、
            # 新しい購読者はストリーム先頭付近の codec config (SPS/PPS 等) が必要。
            # 購読者 0 の状態でストリームが動き続けると、途中参加になり白画面になることがあるので、
            # 0→1 の遷移時はセッションをリスタートして「先頭から」配信する。
            async with self._lock:
                total_subscribers = len(self._subscribers)
                should_restart = self._running and total_subscribers == 0 and self._stats.chunks_sent > 0

            if should_restart:
                logger.info(f"Restarting stream session for fresh subscriber: {self.serial}")
                await self.stop()
                await self.start()

            # 既に誰かが視聴中なら、GOPスナップショットをキューに先に詰めてから購読者登録する。
            # (ロック中に詰めることで、スナップショットとライブデータの順序が崩れない)
            async with self._lock:
                late_join = len(self._subscribers) > 0
                gop_snapshot = list(self._gop_nals) if (late_join and self._gop_has_idr) else []
                # スナップショット分 + 余裕
                qsize = max(200, len(gop_snapshot) + 200)
                queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=qsize)

                for nal in gop_snapshot:
                    try:
                        queue.put_nowait(nal)
                    except asyncio.QueueFull:
                        # 想定外: 初期化塊が入らないと意味がないので、ここは落とす
                        raise RuntimeError("GOP snapshot queue overflow")

                self._subscribers.append(queue)
                self._stats.subscriber_count = len(self._subscribers)
                state = "late-join" if late_join else "active"

            logger.info(
                f"New subscriber for {self.serial}. state={state} subscribers={len(self._subscribers)} gop_prefill_nals={len(gop_snapshot)}"
            )
        
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    if not self._running:
                        break
                    continue

                if not chunk:  # 終了シグナル
                    break
                yield chunk
        finally:
            async with self._lock:
                if queue in self._subscribers:
                    self._subscribers.remove(queue)
                self._stats.subscriber_count = len(self._subscribers)

                subscribers = len(self._subscribers)
            logger.info(f"Subscriber removed for {self.serial}. subscribers={subscribers}")
            
            # 購読者がいなくなったら遅延停止
            if subscribers == 0:
                if self._delayed_stop_task:
                    self._delayed_stop_task.cancel()
                self._delayed_stop_task = asyncio.create_task(self._delayed_stop())
    
    async def _delayed_stop(self) -> None:
        """遅延停止（再接続の猶予）"""
        try:
            await asyncio.sleep(5.0)
            async with self._lock:
                should_stop = len(self._subscribers) == 0
            if should_stop:
                await self.stop()
        finally:
            self._delayed_stop_task = None

    def _update_gop_cache(self, nal: bytes) -> None:
        nal_t = _nal_type(nal)
        if nal_t is None:
            return

        if nal_t == 7:  # SPS
            self._last_sps = nal
            return
        if nal_t == 8:  # PPS
            self._last_pps = nal
            return

        # AUD/SEI は直近VCL前のprefixとして保持（IDRに添える）
        if nal_t in (6, 9):
            self._au_prefix.append(nal)
            # prefix が肥大化しないように上限
            if len(self._au_prefix) > 16:
                self._au_prefix = self._au_prefix[-16:]
            return

        # VCL
        if nal_t == 5:  # IDR
            # 新しいGOP開始: SPS/PPSを先頭に固定し、直前のAUD/SEIを添える
            gop: list[bytes] = []
            if self._last_sps:
                gop.append(self._last_sps)
            if self._last_pps:
                gop.append(self._last_pps)
            gop.extend(self._au_prefix)
            gop.append(nal)
            self._au_prefix.clear()

            self._gop_nals = gop
            self._gop_bytes = sum(len(x) for x in gop)
            self._gop_has_idr = True
            return

        if nal_t == 1:  # non-IDR slice
            self._au_prefix.clear()
            if self._gop_has_idr:
                self._gop_nals.append(nal)
                self._gop_bytes += len(nal)
                if self._gop_bytes > self._gop_max_bytes:
                    # 大きすぎるGOPは late join の初期化塊として扱えないので捨てる
                    self._gop_nals.clear()
                    self._gop_bytes = 0
                    self._gop_has_idr = False
            return

        # その他のNALは、GOPが始まっていればそのまま追記（JMuxer側で必要になる可能性がある）
        if self._gop_has_idr:
            self._gop_nals.append(nal)
            self._gop_bytes += len(nal)
            if self._gop_bytes > self._gop_max_bytes:
                self._gop_nals.clear()
                self._gop_bytes = 0
                self._gop_has_idr = False
    
    async def _run_broadcast(self) -> None:
        """データを全購読者にブロードキャスト"""
        if not self._client:
            return
        
        try:
            async for chunk in self._client.stream():
                if not self._running:
                    break
                
                # raw chunk を NAL unit に分解して配信する（late join の順序保証のため）
                nals = self._extractor.push(chunk)
                for nal in nals:
                    self._update_gop_cache(nal)

                    self._stats.bytes_sent += len(nal)
                    self._stats.chunks_sent += 1

                    async with self._lock:
                        subscribers = list(self._subscribers)

                    for queue in subscribers:
                        try:
                            queue.put_nowait(nal)
                        except asyncio.QueueFull:
                            # 追いつけないクライアントはドロップ（他への配信を優先）
                            pass
        except Exception as e:
            logger.error(f"Broadcast error for {self.serial}: {e}")
        finally:
            self._running = False
    
    @property
    def is_running(self) -> bool:
        """セッションが起動中かどうか"""
        return self._running
    
    @property
    def subscriber_count(self) -> int:
        """現在の購読者数"""
        return len(self._subscribers)
    
    @property
    def stats(self) -> StreamStats:
        """ストリーム統計情報"""
        return self._stats


class StreamManager:
    """全デバイスのストリームセッションを管理
    
    Examples:
        manager = StreamManager(server_jar="path/to/jar")
        
        # セッション取得または作成
        session = await manager.get_or_create("emulator-5554")
        
        # 購読
        async for chunk in session.subscribe():
            await websocket.send_bytes(chunk)
        
        # 全停止
        await manager.stop_all()
    """
    
    def __init__(
        self,
        server_jar: str,
        default_config: Optional[StreamConfig] = None,
    ):
        """
        Args:
            server_jar: ローカルの scrcpy-server.jar ファイルパス
            default_config: デフォルトのストリーミング設定
        """
        self.server_jar = server_jar
        self.default_config = default_config or StreamConfig()
        self._sessions: dict[str, StreamSession] = {}
        self._lock = asyncio.Lock()
    
    async def get_or_create(
        self,
        serial: str,
        config: Optional[StreamConfig] = None,
    ) -> StreamSession:
        """セッションを取得または作成
        
        Args:
            serial: Android デバイスのシリアル番号
            config: ストリーミング設定 (省略時はデフォルト)
        
        Returns:
            StreamSession: ストリームセッション
        """
        async with self._lock:
            if serial in self._sessions:
                session = self._sessions[serial]
                if session.is_running:
                    return session
                # 停止していたら削除して再作成
                try:
                    await session.stop()
                except Exception:
                    pass
                del self._sessions[serial]
            
            session = StreamSession(
                serial=serial,
                server_jar=self.server_jar,
                config=config or self.default_config,
            )
            await session.start()
            self._sessions[serial] = session
            return session
    
    async def stop_session(self, serial: str) -> None:
        """セッションを停止"""
        async with self._lock:
            if serial in self._sessions:
                session = self._sessions.pop(serial)
                await session.stop()
    
    async def stop_all(self) -> None:
        """全セッションを停止"""
        async with self._lock:
            for session in self._sessions.values():
                await session.stop()
            self._sessions.clear()
    
    def get_session(self, serial: str) -> Optional[StreamSession]:
        """セッションを取得 (存在しない場合は None)"""
        return self._sessions.get(serial)
    
    @property
    def active_sessions(self) -> list[str]:
        """アクティブなセッションのシリアル番号リスト"""
        return [s for s, session in self._sessions.items() if session.is_running]
