"""Stream session endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.schemas.session import SessionInfo, SessionsResponse

router = APIRouter()


@router.get("/sessions", response_model=SessionsResponse, summary="List active stream sessions")
async def list_sessions(request: Request) -> SessionsResponse:
    stream_manager = getattr(request.app.state, "stream_manager", None)
    if not stream_manager:
        return SessionsResponse(sessions=[])

    worker_registry = getattr(request.app.state, "worker_registry", None)
    capture_manager = getattr(request.app.state, "capture_manager", None)

    capture_running_by_serial: dict[str, bool] = {}
    if capture_manager is not None:
        capture_running_by_serial = await capture_manager.snapshot_running()

    states = []
    if worker_registry:
        states = await worker_registry.snapshot()

    states_by_serial = {s.serial: s for s in states}

    # include sessions that are running even if registry has no entry yet
    serials = set(stream_manager.active_sessions) | set(states_by_serial.keys())

    sessions: list[SessionInfo] = []
    for serial in sorted(serials):
        st = states_by_serial.get(serial)

        session = stream_manager.get_session(serial)
        stream_running = bool(session and session.is_running)
        stream_subscribers = int(session.subscriber_count) if session else 0

        capture_running = bool(capture_running_by_serial.get(serial, False))

        sessions.append(
            SessionInfo(
                serial=serial,
                stream_running=stream_running,
                stream_subscribers=stream_subscribers,
                stream_clients=int(st.stream_clients) if st else 0,
                capture_clients=int(st.capture_clients) if st else 0,
                capture_running=capture_running,
            )
        )

    return SessionsResponse(sessions=sessions)
