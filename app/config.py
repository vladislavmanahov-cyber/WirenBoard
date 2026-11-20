"""Настройки сервиса. Всё берётся из переменных окружения."""
import os
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass
class Settings:
    # MQTT-брокер контроллера Wiren Board (по умолчанию на самом контроллере, порт 1883).
    # Пустой MQTT_HOST — сервис стартует без подключения (удобно для тестов и вёрстки панели).
    mqtt_host: str = field(default_factory=lambda: _env("MQTT_HOST"))
    mqtt_port: int = field(default_factory=lambda: int(_env("MQTT_PORT", "1883") or 1883))
    mqtt_user: str = field(default_factory=lambda: _env("MQTT_USER"))
    mqtt_password: str = field(default_factory=lambda: _env("MQTT_PASSWORD"))
    mqtt_tls: bool = field(default_factory=lambda: _env("MQTT_TLS", "0") == "1")
    # Пароль на панель (HTTP Basic, логин любой). Пустой — панель открыта: только для локальной разработки.
    panel_password: str = field(default_factory=lambda: _env("PANEL_PASSWORD"))


settings = Settings()
