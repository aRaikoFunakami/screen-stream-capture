"""API schemas for device endpoints."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DeviceState(str, Enum):
    """Device connection state as exposed via API."""

    device = "device"
    offline = "offline"
    unauthorized = "unauthorized"
    connecting = "connecting"
    unknown = "unknown"


class Device(BaseModel):
    """Device info returned by the backend API."""

    model_config = ConfigDict(populate_by_name=True)

    serial: str = Field(description="ADB device serial")
    state: DeviceState = Field(description="Connection state")
    model: str | None = Field(default=None, description="Device model")
    manufacturer: str | None = Field(default=None, description="Device manufacturer")
    is_emulator: bool = Field(alias="isEmulator", description="Whether this is an emulator")
    last_seen: datetime = Field(alias="lastSeen", description="Last time the device was seen")


class HealthzResponse(BaseModel):
    status: str
    version: str
