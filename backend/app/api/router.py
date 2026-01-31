"""Top-level API router (prefixed under /api)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.endpoints import capture, devices, events, latency, sessions, stream

api_router = APIRouter(prefix="/api")

api_router.include_router(devices.router, tags=["devices"])
api_router.include_router(events.router, tags=["events"])
api_router.include_router(sessions.router, tags=["sessions"])
api_router.include_router(stream.router, tags=["stream"])
api_router.include_router(capture.router, tags=["capture"])
api_router.include_router(latency.router, tags=["latency"])
