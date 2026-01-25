"""API schemas for stream sessions."""

from __future__ import annotations

from pydantic import BaseModel


class SessionsResponse(BaseModel):
    sessions: list[str]
