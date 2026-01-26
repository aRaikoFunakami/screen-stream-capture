"""API schemas for stream sessions."""

from __future__ import annotations

from pydantic import BaseModel


class SessionInfo(BaseModel):
    serial: str
    stream_running: bool
    stream_subscribers: int
    stream_clients: int
    capture_clients: int
    capture_running: bool


class SessionsResponse(BaseModel):
    sessions: list[SessionInfo]
