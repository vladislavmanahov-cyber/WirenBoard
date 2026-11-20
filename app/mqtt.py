"""Подключение к MQTT-брокеру контроллера: читает /devices/#, отправляет команды в .../on."""
from __future__ import annotations

import asyncio
import logging
import ssl

import aiomqtt

from .config import Settings
from .store import SUBSCRIBE_TOPIC, DeviceStore, set_topic

log = logging.getLogger("wb.mqtt")


class MqttBridge:
    def __init__(self, cfg: Settings, store: DeviceStore) -> None:
        self.cfg = cfg
        self.store = store
        self._client: aiomqtt.Client | None = None
        self.connected = asyncio.Event()

    def _make_client(self) -> aiomqtt.Client:
        return aiomqtt.Client(
            hostname=self.cfg.mqtt_host,
            port=self.cfg.mqtt_port,
            username=self.cfg.mqtt_user or None,
            password=self.cfg.mqtt_password or None,
            tls_context=ssl.create_default_context() if self.cfg.mqtt_tls else None,
            identifier=None,
        )

    async def run(self) -> None:
        """Держит подключение: при обрыве переподключается с нарастающей паузой (до 30 с)."""
        delay = 1
        while True:
            try:
                async with self._make_client() as client:
                    self._client = client
                    await client.subscribe(SUBSCRIBE_TOPIC)
                    self.connected.set()
                    log.info("MQTT: подключено к %s:%s", self.cfg.mqtt_host, self.cfg.mqtt_port)
                    delay = 1
                    async for msg in client.messages:
                        self.store.handle(str(msg.topic), msg.payload or b"")
            except aiomqtt.MqttError as e:
                log.warning("MQTT: нет связи (%s), повтор через %s с", e, delay)
            finally:
                self._client = None
                self.connected.clear()
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

    async def publish_set(self, device: str, control: str, value: str) -> None:
        if self._client is None:
            raise ConnectionError("нет связи с контроллером")
        await self._client.publish(set_topic(device, control), value, qos=1)
