# WirenBoard

Сервис и веб-панель для контроллера [Wiren Board](https://wirenboard.com/ru/): показывает устройства и их
показания в реальном времени, позволяет переключать реле, менять яркость, нажимать кнопки.

Python 3.12, FastAPI, aiomqtt. Панель — обычные HTML/JS в `app/static`, обновления приходят через Server-Sent Events.

## Как устроено

Контроллер публикует всё в свой MQTT-брокер (Mosquitto, порт 1883) по соглашениям Wiren Board:

| Топик | Что это |
|---|---|
| `/devices/<устройство>/meta` | описание устройства (название) |
| `/devices/<устройство>/controls/<контрол>` | текущее значение |
| `/devices/<устройство>/controls/<контрол>/meta` | тип, единицы, min/max, только чтение |
| `/devices/<устройство>/controls/<контрол>/on` | команда: установить значение |

Сервис подписывается на `/devices/#`, держит состояние в памяти (`app/store.py`) и отдаёт его панели.
Команды из панели уходят в `.../on` (`app/mqtt.py`).

Устройства на шине RS-485 (Modbus) контроллер сам опрашивает через `wb-mqtt-serial` и выкладывает в тот же MQTT,
поэтому отдельный Modbus-клиент сервису не нужен. Если понадобится опрашивать Modbus TCP напрямую — можно добавить `pymodbus`.

## Локальный запуск без контроллера

Нужен брокер Mosquitto (`apt install mosquitto` или `brew install mosquitto`).

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
```

```bash
mosquitto -p 1883 -d
```

```bash
.venv/bin/python tools/simulator.py
```

```bash
MQTT_HOST=localhost .venv/bin/uvicorn app.main:app --port 8080
```

Панель: http://localhost:8080. Симулятор (`tools/simulator.py`) изображает реле, датчик и диммер.

## С настоящим контроллером

```bash
MQTT_HOST=192.168.1.10 PANEL_PASSWORD=придумайте .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Настройки (переменные окружения)

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `MQTT_HOST` | пусто | адрес брокера контроллера; пусто — без подключения |
| `MQTT_PORT` | `1883` | порт брокера |
| `MQTT_USER`, `MQTT_PASSWORD` | пусто | если на брокере включена авторизация |
| `MQTT_TLS` | `0` | `1` — подключаться по TLS |
| `PANEL_PASSWORD` | пусто | пароль на панель (HTTP Basic, логин любой). Пусто — панель открыта всем |

## Тесты

```bash
.venv/bin/python -m pytest -q
```

Тест `test_mqtt_integration.py` поднимает настоящий Mosquitto с симулятором; без установленного `mosquitto` он пропускается.
