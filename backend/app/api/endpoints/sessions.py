"""Stream session endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.schemas.session import SessionsResponse

router = APIRouter()


@router.get("/sessions", response_model=SessionsResponse, summary="List active stream sessions")
async def list_sessions(request: Request) -> SessionsResponse:
    stream_manager = getattr(request.app.state, "stream_manager", None)
    if not stream_manager:
        return SessionsResponse(sessions=[])
    return SessionsResponse(sessions=stream_manager.active_sessions)
