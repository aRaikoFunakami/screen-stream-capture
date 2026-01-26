from __future__ import annotations

import json


def _extract_first_event(chunk: str) -> tuple[str, str]:
    # expects: event: <name>\ndata: <json>\n\n
    lines = [ln for ln in chunk.splitlines() if ln.strip()]
    assert lines[0].startswith("event: ")
    assert lines[1].startswith("data: ")
    return lines[0].removeprefix("event: "), lines[1].removeprefix("data: ")


def test_events_sends_initial_devices_snapshot(client):
    with client.stream("GET", "/api/events") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")

        first = next(r.iter_text())

    event_name, data = _extract_first_event(first)
    assert event_name == "devices"

    devices = json.loads(data)
    assert isinstance(devices, list)
    assert len(devices) == 1
    assert devices[0]["serial"] == "ABC123"
