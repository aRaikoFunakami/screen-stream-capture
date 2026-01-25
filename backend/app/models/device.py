"""Device domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class DeviceState(str, Enum):
    """デバイスの接続状態"""

    DEVICE = "device"
    OFFLINE = "offline"
    UNAUTHORIZED = "unauthorized"
    CONNECTING = "connecting"
    UNKNOWN = "unknown"


@dataclass
class DeviceInfo:
    """デバイス情報"""

    serial: str
    state: DeviceState = DeviceState.UNKNOWN
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    is_emulator: bool = False
    last_seen: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "serial": self.serial,
            "state": self.state.value,
            "model": self.model,
            "manufacturer": self.manufacturer,
            "isEmulator": self.is_emulator,
            "lastSeen": self.last_seen.isoformat(),
        }
