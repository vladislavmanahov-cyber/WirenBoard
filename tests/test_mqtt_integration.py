"""Связка с настоящим брокером: mosquitto + симулятор контроллера. Пропускается, если mosquitto не установлен."""
import asyncio
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import Settings
from app.mqtt import MqttBridge
from app.store import DeviceStore

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(shutil.which("mosquitto") is None, reason="mosquitto не установлен")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _wait(cond, timeout=10.0):
    for _ in range(int(timeout / 0.05)):
        if cond():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("не дождались")


@pytest.fixture
def broker(tmp_path):
    port = _free_port()
    conf = tmp_path / "m.conf"
    conf.write_text(f"listener {port} 127.0.0.1\nallow_anonymous true\n")
    p = subprocess.Popen(["mosquitto", "-c", str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        subprocess.run(["sleep", "0.05"])
    yield port
    p.terminate()
    p.wait()


def test_bridge_with_simulator(broker):
    async def scenario():
        sim = await asyncio.create_subprocess_exec(
            sys.executable, str(ROOT / "tools" / "simulator.py"), "--host", "127.0.0.1", "--port", str(broker),
            "--period", "0.2", stdout=asyncio.subprocess.DEVNULL)
        store = DeviceStore()
        bridge = MqttBridge(Settings(mqtt_host="127.0.0.1", mqtt_port=broker), store)
        task = asyncio.create_task(bridge.run())
        try:
            await _wait(lambda: (c := store.get_control("wb-mr6c_21", "K1")) and c.value == "0" and c.type == "switch")
            assert store.devices["wb-msw-v3_34"].title == "Датчик WB-MSW v3 (зал)"
            await bridge.publish_set("wb-mr6c_21", "K1", "1")
            await _wait(lambda: store.get_control("wb-mr6c_21", "K1").value == "1")
        finally:
            task.cancel()
            sim.terminate()
            await sim.wait()

    asyncio.run(scenario())
