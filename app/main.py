"""Веб-панель и API для контроллера Wiren Board."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import settings
from .mqtt import MqttBridge
from .store import DeviceStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
STATIC = Path(__file__).parent / "static"

store = DeviceStore()
bridge = MqttBridge(settings, store)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(bridge.run()) if settings.mqtt_host else None
    try:
        yield
    finally:
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="Wiren Board панель", lifespan=lifespan, docs_url=None, redoc_url=None)
_basic = HTTPBasic(auto_error=False)


def require_auth(creds: HTTPBasicCredentials | None = Depends(_basic)) -> None:
    if not settings.panel_password:
        return
    if creds is None or not secrets.compare_digest(creds.password.encode(), settings.panel_password.encode()):
        raise HTTPException(401, "Нужен пароль", headers={"WWW-Authenticate": 'Basic realm="wirenboard"'})


class SetValue(BaseModel):
    value: str


@app.get("/api/status", dependencies=[Depends(require_auth)])
def status():
    return {"mqtt_configured": bool(settings.mqtt_host), "connected": bridge.connected.is_set()}


@app.get("/api/devices", dependencies=[Depends(require_auth)])
def devices():
    return store.snapshot()


@app.post("/api/devices/{device}/controls/{control}", dependencies=[Depends(require_auth)])
async def set_control(device: str, control: str, body: SetValue):
    ctrl = store.get_control(device, control)
    if ctrl is None:
        raise HTTPException(404, "Нет такого контрола")
    if not ctrl.writable:
        raise HTTPException(403, "Контрол только для чтения")
    if ctrl.type == "switch" and body.value not in ("0", "1"):
        raise HTTPException(422, "Для переключателя нужно 0 или 1")
    if ctrl.type == "range":
        try:
            v = float(body.value)
        except ValueError:
            raise HTTPException(422, "Нужно число") from None
        if (ctrl.min is not None and v < ctrl.min) or (ctrl.max is not None and v > ctrl.max):
            raise HTTPException(422, "Значение вне диапазона")
    try:
        await bridge.publish_set(device, control, body.value)
    except ConnectionError as e:
        raise HTTPException(503, str(e)) from None
    return {"ok": True}


@app.get("/api/events", dependencies=[Depends(require_auth)])
async def events(request: Request):
    """Поток изменений для панели (Server-Sent Events). Первым приходит полный снимок."""
    q = store.subscribe()

    async def stream():
        try:
            yield f"event: snapshot\ndata: {json.dumps(store.snapshot(), ensure_ascii=False)}\n\n"
            while not await request.is_disconnected():
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield f"event: {ev['kind']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            store.unsubscribe(q)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/", dependencies=[Depends(require_auth)])
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
