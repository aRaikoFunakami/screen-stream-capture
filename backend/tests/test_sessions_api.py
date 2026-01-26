from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator


def test_sessions_empty_when_no_manager(monkeypatch, app):
    # remove stream_manager from state
    if hasattr(app.state, "stream_manager"):
        delattr(app.state, "stream_manager")

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        r = client.get("/api/sessions")
        assert r.status_code == 200
        assert r.json() == {"sessions": []}


def test_sessions_includes_registry_and_capture_state(client, app):
    # Add a second serial only in registry (no running stream session)
    import asyncio


    @dataclass
    class _LocalStreamSession:
        is_running: bool = True
        subscriber_count: int = 0

        async def subscribe(self) -> AsyncIterator[bytes]:
            if False:  # pragma: no cover
                yield b""

    async def setup() -> None:
        await app.state.worker_registry.on_stream_connect("ONLY_REG")
        await app.state.worker_registry.on_capture_connect("ONLY_REG")

        # Mark capture running for ONLY_REG as well
        await app.state.capture_manager.acquire("ONLY_REG")

        # Stream session for ABC123 already exists; set subscribers
        session = app.state.stream_manager.get_session("ABC123")
        assert session is not None
        session.subscriber_count = 3

        # Create stream session object but mark not running
        s2 = _LocalStreamSession(is_running=False)
        app.state.stream_manager.set_session("NOT_RUNNING", s2)

    asyncio.run(setup())

    r = client.get("/api/sessions")
    assert r.status_code == 200
    payload = r.json()
    assert "sessions" in payload

    by_serial = {s["serial"]: s for s in payload["sessions"]}

    assert by_serial["ABC123"]["stream_running"] is True
    assert by_serial["ABC123"]["stream_subscribers"] == 3

    assert by_serial["ONLY_REG"]["stream_clients"] == 1
    assert by_serial["ONLY_REG"]["capture_clients"] == 1
    assert by_serial["ONLY_REG"]["capture_running"] is True

    assert by_serial["NOT_RUNNING"]["stream_running"] is False
