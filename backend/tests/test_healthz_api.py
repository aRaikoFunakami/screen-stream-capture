from __future__ import annotations


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "0.1.0"}


def test_healthz_legacy_path(client):
    r = client.get("/api/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
