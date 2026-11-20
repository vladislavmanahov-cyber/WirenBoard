import json

from app.store import DeviceStore


def test_new_style_meta():
    s = DeviceStore()
    s.handle("/devices/wb-mr6c_21/meta", json.dumps({"title": {"en": "Relay", "ru": "Реле"}}))
    s.handle("/devices/wb-mr6c_21/controls/K1/meta", json.dumps({"type": "switch", "order": 1, "title": {"ru": "Свет"}}))
    s.handle("/devices/wb-mr6c_21/controls/K1", b"1")
    [dev] = s.snapshot()
    assert dev["title"] == "Реле"
    [c] = dev["controls"]
    assert (c["id"], c["value"], c["type"], c["title"], c["writable"]) == ("K1", "1", "switch", "Свет", True)


def test_old_style_meta_and_readonly():
    s = DeviceStore()
    s.handle("/devices/wb-msw/meta/name", "Датчик")
    s.handle("/devices/wb-msw/controls/Temperature/meta/type", "temperature")
    s.handle("/devices/wb-msw/controls/Temperature/meta/readonly", "1")
    s.handle("/devices/wb-msw/controls/Temperature/meta/units", "°C")
    s.handle("/devices/wb-msw/controls/Temperature", "22.5")
    c = s.get_control("wb-msw", "Temperature")
    assert c.readonly and not c.writable and c.units == "°C" and c.value == "22.5"
    assert s.snapshot()[0]["title"] == "Датчик"


def test_ignores_commands_and_foreign_topics():
    s = DeviceStore()
    assert s.handle("/devices/d/controls/K1/on", "1") is None
    assert s.handle("/other/topic", "x") is None
    assert s.devices == {}


def test_empty_retained_removes_control():
    s = DeviceStore()
    s.handle("/devices/d/controls/K1", "1")
    s.handle("/devices/d/controls/K1", "")
    assert s.get_control("d", "K1") is None


def test_control_order():
    s = DeviceStore()
    s.handle("/devices/d/controls/b/meta", json.dumps({"order": 1}))
    s.handle("/devices/d/controls/a/meta", json.dumps({"order": 2}))
    s.handle("/devices/d/controls/c", "x")
    assert [c["id"] for c in s.snapshot()[0]["controls"]] == ["b", "a", "c"]


def test_bad_json_meta_is_ignored():
    s = DeviceStore()
    s.handle("/devices/d/controls/K1/meta", "{not json")
    assert s.get_control("d", "K1").type == "value"
