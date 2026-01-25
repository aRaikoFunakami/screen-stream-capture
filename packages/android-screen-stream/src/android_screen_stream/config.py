"""
StreamConfig - ストリーミング設定

解像度、フレームレート、ビットレートなどの設定を管理
"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class StreamConfig:
    """ストリーミング設定
    
    Attributes:
        max_size: 短辺の最大ピクセル数 (例: 720, 1080, 1440)
        max_fps: 最大フレームレート (例: 15, 30, 60)
        bit_rate: ビットレート (bps) (例: 2_000_000 = 2Mbps)
        video_codec: ビデオコーデック ("h264", "h265", "av1")
    
    Examples:
        # デフォルト設定
        config = StreamConfig()
        
        # カスタム設定
        config = StreamConfig(max_size=1080, max_fps=60, bit_rate=8_000_000)
        
        # プリセット使用
        config = StreamConfig.high_quality()
    """
    max_size: int = 720
    max_fps: int = 30
    bit_rate: int = 2_000_000
    video_codec: Literal["h264", "h265", "av1"] = "h264"
    
    def __post_init__(self) -> None:
        """バリデーション"""
        if self.max_size < 1:
            raise ValueError(f"max_size must be positive: {self.max_size}")
        if self.max_fps < 1:
            raise ValueError(f"max_fps must be positive: {self.max_fps}")
        if self.bit_rate < 1:
            raise ValueError(f"bit_rate must be positive: {self.bit_rate}")
        if self.video_codec not in ("h264", "h265", "av1"):
            raise ValueError(f"Invalid video_codec: {self.video_codec}")
    
    @classmethod
    def low_bandwidth(cls) -> "StreamConfig":
        """低帯域向けプリセット (720p, 15fps, 1Mbps)
        
        モバイル回線や帯域が限られた環境向け
        """
        return cls(max_size=720, max_fps=15, bit_rate=1_000_000)
    
    @classmethod
    def balanced(cls) -> "StreamConfig":
        """バランスプリセット (1080p, 30fps, 4Mbps)
        
        一般的な用途向け
        """
        return cls(max_size=1080, max_fps=30, bit_rate=4_000_000)
    
    @classmethod
    def high_quality(cls) -> "StreamConfig":
        """高品質プリセット (1080p, 60fps, 8Mbps)
        
        高帯域環境での高品質ストリーミング向け
        """
        return cls(max_size=1080, max_fps=60, bit_rate=8_000_000)
    
    def to_scrcpy_args(self) -> list[str]:
        """scrcpy-server用の引数リストを生成"""
        args = [
            f"max_size={self.max_size}",
            f"max_fps={self.max_fps}",
            f"video_bit_rate={self.bit_rate}",
        ]
        if self.video_codec != "h264":
            args.append(f"video_codec={self.video_codec}")
        return args
