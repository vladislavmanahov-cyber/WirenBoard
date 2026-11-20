"""Имитация контроллера Wiren Board: публикует устройства в MQTT по его соглашениям и отвечает на команды.

Нужен, чтобы разрабатывать панель без настоящего контроллера:
    mosquitto -p 1883 -d
    python tools/simulator.py --host localhost
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random

import aiomqtt

DEVICES = {
    "wb-mr6c_21": {
        "title": "Реле WB-MR6C (кухня)",
        "controls": {
            f"K{i}": {"meta": {"type": "switch", "order": i, "title": {"ru": f"Реле {i}"}}, "value": "0"}
            for i in range(1, 4)
        },
    },
    "wb-msw-v3_34": {
        "title": "Датчик WB-MSW v3 (зал)",
        "controls": {
            "Temperature": {"meta": {"type": "temperature", "readonly": True, "order": 1, "title": {"ru": "Температура"}, "units": "°C"}, "value": "22.4"},
            "Humidity": {"meta": {"type": "rel_humidity", "readonly": True, "order": 2, "title": {"ru": "Влажность"}, "units": "%"}, "value": "41"},
            "CO2": {"meta": {"type": "concentration", "readonly": True, "order": 3, "title": {"ru": "CO₂"}, "units": "ppm"}, "value": "640"},
        },
    },
    "wb-mdm3_58": {
        "title": "Диммер WB-MDM3 (вывеска)",
        "controls": {
            "Channel 1": {"meta": {"type": "range", "min": 0, "max": 100, "order": 1, "title": {"ru": "Яркость"}, "units": "%"}, "value": "70"},
            "Reset": {"meta": {"type": "pushbutton", "order": 2, "title": {"ru": "Сброс"}}, "value": "0"},
        },
    },
}


async def publish_all(client: aiomqtt.Client) -> None:
    for dev, d in DEVICES.items():
        await client.publish(f"/devices/{dev}/meta", json.dumps({"driver": "simulator", "title": {"ru": d["title"]}}), retain=True)
        for ctrl, c in d["controls"].items():
            await client.publish(f"/devices/{dev}/controls/{ctrl}/meta", json.dumps(c["meta"]), retain=True)
            await client.publish(f"/devices/{dev}/controls/{ctrl}", c["value"], retain=True)


async def drift(client: aiomqtt.Client, period: float) -> None:
    """Медленно меняет показания датчика, чтобы было видно обновления в панели."""
    while True:
        await asyncio.sleep(period)
        ctrls = DEVICES["wb-msw-v3_34"]["controls"]
        t = float(ctrls["Temperature"]["value"]) + random.uniform(-0.3, 0.3)
        ctrls["Temperature"]["value"] = f"{t:.1f}"
        await client.publish("/devices/wb-msw-v3_34/controls/Temperature", ctrls["Temperature"]["value"], retain=True)


async def main(host: str, port: int, period: float) -> None:
    async with aiomqtt.Client(host, port) as client:
        await publish_all(client)
        await client.subscribe("/devices/+/controls/+/on")
        print(f"Симулятор работает: {host}:{port}, устройств {len(DEVICES)}")
        task = asyncio.create_task(drift(client, period))
        try:
            async for msg in client.messages:
                _, _, dev, _, ctrl, _ = str(msg.topic).split("/")
                c = DEVICES.get(dev, {}).get("controls", {}).get(ctrl)
                if not c or c["meta"].get("readonly"):
                    continue
                value = (msg.payload or b"").decode()
                if c["meta"]["type"] == "pushbutton":
                    print(f"нажата кнопка {dev}/{ctrl}")
                    continue
                c["value"] = value
                await client.publish(f"/devices/{dev}/controls/{ctrl}", value, retain=True)
        finally:
            task.cancel()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--period", type=float, default=3.0, help="как часто меняются показания датчика, секунд")
    a = p.parse_args()
    asyncio.run(main(a.host, a.port, a.period))
