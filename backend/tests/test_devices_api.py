from __future__ import annotations


def test_list_devices(client):
    r = client.get("/api/devices")
    assert r.status_code == 200
    payload = r.json()
    assert isinstance(payload, list)
    assert len(payload) == 1
    d0 = payload[0]
    assert d0["serial"] == "ABC123"
    assert d0["state"] == "device"
    assert "lastSeen" in d0


def test_get_device_found(client):
    r = client.get("/api/devices/ABC123")
    assert r.status_code == 200
    d = r.json()
    assert d["serial"] == "ABC123"


def test_get_device_not_found(client):
    r = client.get("/api/devices/NOPE")
    assert r.status_code == 404
    assert r.json()["detail"] == "Device NOPE not found"
