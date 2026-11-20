import json

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(monkeypatch):
    main.store.devices.clear()
    sent = []

    async def fake_publish(device, control, value):
        sent.append((device, control, value))

    monkeypatch.setattr(main.bridge, "publish_set", fake_publish)
    monkeypatch.setattr(main.settings, "panel_password", "")
    main.store.handle("/devices/r/controls/K1/meta", json.dumps({"type": "switch"}))
    main.store.handle("/devices/r/controls/K1", "0")
    main.store.handle("/devices/r/controls/Dim/meta", json.dumps({"type": "range", "min": 0, "max": 100}))
    main.store.handle("/devices/s/controls/T/meta", json.dumps({"type": "temperature", "readonly": True}))
    with TestClient(main.app) as c:
        c.sent = sent
        yield c


def test_devices_list(client):
    ids = [d["id"] for d in client.get("/api/devices").json()]
    assert ids == ["r", "s"]


def test_set_switch(client):
    assert client.post("/api/devices/r/controls/K1", json={"value": "1"}).status_code == 200
    assert client.sent == [("r", "K1", "1")]


def test_validation(client):
    assert client.post("/api/devices/r/controls/K1", json={"value": "5"}).status_code == 422
    assert client.post("/api/devices/r/controls/Dim", json={"value": "150"}).status_code == 422
    assert client.post("/api/devices/s/controls/T", json={"value": "1"}).status_code == 403
    assert client.post("/api/devices/x/controls/y", json={"value": "1"}).status_code == 404
    assert client.sent == []


def test_password(client, monkeypatch):
    monkeypatch.setattr(main.settings, "panel_password", "secret")
    assert client.get("/api/devices").status_code == 401
    assert client.get("/api/devices", auth=("any", "wrong")).status_code == 401
    assert client.get("/api/devices", auth=("any", "secret")).status_code == 200


def test_index(client):
    r = client.get("/")
    assert r.status_code == 200 and "Wiren Board" in r.text
