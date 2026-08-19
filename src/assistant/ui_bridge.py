"""Two-way bridge to the Electron frontend over a local WebSocket, if it's
running. The backend works fine with no UI attached at all — outgoing
broadcast is best-effort; incoming commands (device/volume/sleep/power)
are the only way those settings actually change, so main.py wires real
handlers for them.
"""

import asyncio
import json
import threading

import sounddevice as sd
import websockets

from . import settings

_clients = set()
_loop = None
_command_handlers = {}


def on_command(msg_type):
    """Decorator: register a handler for an incoming {"type": msg_type, ...} message."""

    def wrap(func):
        _command_handlers[msg_type] = func
        return func

    return wrap


def _device_list():
    devices = sd.query_devices()
    inputs = [{"index": i, "name": d["name"]} for i, d in enumerate(devices) if d["max_input_channels"] > 0]
    outputs = [{"index": i, "name": d["name"]} for i, d in enumerate(devices) if d["max_output_channels"] > 0]
    return {"type": "devices", "inputs": inputs, "outputs": outputs}


async def _send_initial_state(websocket):
    await websocket.send(json.dumps(_device_list()))
    await websocket.send(json.dumps({"type": "settings", **settings.get_all()}))


async def _handler(websocket):
    _clients.add(websocket)
    try:
        await _send_initial_state(websocket)
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            handler = _command_handlers.get(msg.get("type"))
            if handler:
                handler(msg)
    finally:
        _clients.discard(websocket)


async def _serve():
    async with websockets.serve(_handler, "localhost", 8765):
        await asyncio.Future()  # run forever


def start() -> None:
    global _loop

    def run():
        global _loop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        _loop.run_until_complete(_serve())

    threading.Thread(target=run, daemon=True).start()


def broadcast(state: str, user_text: str = "", reply_text: str = "") -> None:
    _broadcast_json({"type": "state", "state": state, "user_text": user_text, "reply_text": reply_text})


def broadcast_settings() -> None:
    _broadcast_json({"type": "settings", **settings.get_all()})


def _broadcast_json(payload: dict) -> None:
    if _loop is None or not _clients:
        return
    data = json.dumps(payload)

    async def _send():
        for client in list(_clients):
            try:
                await client.send(data)
            except Exception:
                pass

    asyncio.run_coroutine_threadsafe(_send(), _loop)
