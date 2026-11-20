"""Состояние устройств контроллера, собранное из MQTT-топиков Wiren Board.

Соглашения Wiren Board:
  /devices/<устройство>/meta                       JSON: {"title": {"ru": ...}, ...}  (новые прошивки)
  /devices/<устройство>/meta/name                  название (старые прошивки)
  /devices/<устройство>/controls/<контрол>         значение (строка, retained)
  /devices/<устройство>/controls/<контрол>/meta    JSON: {"type", "readonly", "order", "title", "units", "min", "max"}
  /devices/<устройство>/controls/<контрол>/meta/<ключ>  то же по отдельности (старые прошивки)
  /devices/<устройство>/controls/<контрол>/on      команда «установить значение»
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field

SUBSCRIBE_TOPIC = "/devices/#"

# Типы, которые можно менять с панели (если контрол не помечен readonly).
WRITABLE_TYPES = {"switch", "pushbutton", "range", "rgb", "text", "value"}


def set_topic(device: str, control: str) -> str:
    return f"/devices/{device}/controls/{control}/on"


def _title(raw) -> str | None:
    if isinstance(raw, dict):
        return raw.get("ru") or raw.get("en") or next(iter(raw.values()), None)
    return raw or None


@dataclass
class Control:
    id: str
    value: str | None = None
    type: str = "value"
    readonly: bool = False
    title: str | None = None
    units: str | None = None
    min: float | None = None
    max: float | None = None
    order: int | None = None
    error: str | None = None

    @property
    def writable(self) -> bool:
        return not self.readonly and self.type in WRITABLE_TYPES

    def to_dict(self) -> dict:
        return asdict(self) | {"writable": self.writable}


@dataclass
class Device:
    id: str
    title: str | None = None
    controls: dict[str, Control] = field(default_factory=dict)

    def to_dict(self) -> dict:
        ctrls = sorted(self.controls.values(), key=lambda c: (c.order is None, c.order or 0, c.id))
        return {"id": self.id, "title": self.title or self.id, "controls": [c.to_dict() for c in ctrls]}


class DeviceStore:
    def __init__(self) -> None:
        self.devices: dict[str, Device] = {}
        self._listeners: set[asyncio.Queue] = set()

    # --- разбор входящих сообщений ---

    def handle(self, topic: str, payload: bytes | str) -> dict | None:
        """Применяет сообщение. Возвращает событие для панели или None, если топик не наш."""
        text = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload
        parts = topic.strip("/").split("/")
        if len(parts) < 2 or parts[0] != "devices":
            return None
        dev_id = parts[1]
        rest = parts[2:]

        if rest in (["meta"], ["meta", "name"]):
            dev = self._device(dev_id)
            dev.title = self._parse_device_meta(text) if rest == ["meta"] else (text or None)
            return self._emit({"kind": "device", "device": dev.to_dict()})

        if len(rest) >= 2 and rest[0] == "controls":
            ctrl_id = rest[1]
            tail = rest[2:]
            if tail == ["on"]:
                return None  # команда, а не состояние
            if not text and not tail:
                # пустое retained-сообщение — контрол удалён
                dev = self.devices.get(dev_id)
                if dev and dev.controls.pop(ctrl_id, None):
                    return self._emit({"kind": "device", "device": dev.to_dict()})
                return None
            ctrl = self._control(dev_id, ctrl_id)
            if not tail:
                ctrl.value = text
            elif tail == ["meta"]:
                self._apply_control_meta(ctrl, text)
            elif len(tail) == 2 and tail[0] == "meta":
                self._apply_meta_key(ctrl, tail[1], text)
            else:
                return None
            return self._emit({"kind": "control", "device": dev_id, "control": ctrl.to_dict()})
        return None

    def _device(self, dev_id: str) -> Device:
        return self.devices.setdefault(dev_id, Device(dev_id))

    def _control(self, dev_id: str, ctrl_id: str) -> Control:
        return self._device(dev_id).controls.setdefault(ctrl_id, Control(ctrl_id))

    @staticmethod
    def _parse_device_meta(text: str) -> str | None:
        try:
            return _title(json.loads(text).get("title"))
        except (ValueError, AttributeError):
            return None

    def _apply_control_meta(self, ctrl: Control, text: str) -> None:
        try:
            meta = json.loads(text)
        except ValueError:
            return
        if not isinstance(meta, dict):
            return
        for key, val in meta.items():
            self._apply_meta_key(ctrl, key, val)

    @staticmethod
    def _apply_meta_key(ctrl: Control, key: str, val) -> None:
        def num(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        if key == "type":
            ctrl.type = str(val)
        elif key == "readonly":
            ctrl.readonly = val in (True, 1, "1", "true")
        elif key == "title":
            ctrl.title = _title(val)
        elif key == "units":
            ctrl.units = str(val) or None
        elif key in ("min", "max"):
            setattr(ctrl, key, num(val))
        elif key == "order":
            n = num(val)
            ctrl.order = int(n) if n is not None else None
        elif key == "error":
            ctrl.error = str(val) or None

    # --- для API ---

    def snapshot(self) -> list[dict]:
        return [d.to_dict() for d in sorted(self.devices.values(), key=lambda d: (d.title or d.id).lower())]

    def get_control(self, dev_id: str, ctrl_id: str) -> Control | None:
        dev = self.devices.get(dev_id)
        return dev.controls.get(ctrl_id) if dev else None

    # --- подписка панели на изменения (Server-Sent Events) ---

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._listeners.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._listeners.discard(q)

    def _emit(self, event: dict) -> dict:
        for q in list(self._listeners):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # медленный клиент пропустит событие и догонит при переподключении
        return event
