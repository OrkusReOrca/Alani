"""Two-way bridge to the Electron frontend over a local WebSocket, if it's
running. The backend works fine with no UI attached at all — outgoing
broadcast is best-effort; incoming commands (device/volume/sleep/power)
are the only way those settings actually change, so main.py wires real
handlers for them.
"""

import asyncio
import json
import queue
import threading

import sounddevice as sd
import websockets

from . import settings
from .config import VOICE_LABELS

_clients = set()
_loop = None
_command_handlers = {}
_last_state = None  # see broadcast()/_send_initial_state()

# Transient (never persisted) runtime signals for the "force idle" button —
# see main.py's on_command("force_idle") and on_wake(). Separate from
# settings.py on purpose: these are one-shot/session-scoped, not durable
# user preferences.
_cloud_task_active = False
_interrupt_active = False
_console_active = False


def is_cloud_task_active() -> bool:
    return _cloud_task_active


def set_cloud_task_active(active: bool) -> None:
    """Call this around any operation that needs the internet (calendar,
    etc. — none exist yet) so a force-idle click can't cut it off mid-flight."""
    global _cloud_task_active
    _cloud_task_active = active


def is_console_active() -> bool:
    return _console_active


def set_console_active(active: bool) -> None:
    """True while the "console add" manual-entry UI is open (see
    main.py's on_command("open_console")/("close_console")) —
    wake_word/listener.py checks this the same way it checks
    settings.sleep_mode, closing the mic stream entirely while a form is
    open so a wake word can't start a voice turn underneath it."""
    global _console_active
    _console_active = active


def is_interrupt_active() -> bool:
    return _interrupt_active


def request_interrupt() -> None:
    global _interrupt_active
    _interrupt_active = True


def clear_interrupt() -> None:
    global _interrupt_active
    _interrupt_active = False


# Bridges reading-mode's typed input (arrives async, on the websocket's
# event-loop thread) into pipeline.py's turn-processing thread, which
# needs to block waiting for it the same way record.record_until_silence()
# blocks waiting for audio — see wait_for_text_input()'s polling loop,
# which mirrors that function's instant-cutoff pattern.
_text_input_queue = queue.Queue()


def submit_text_input(text: str) -> None:
    _text_input_queue.put(text)


def wait_for_text_input(poll_interval: float = 0.1):
    """Blocks until text is submitted via the UI's reading-mode input, or
    power_on/interrupt aborts (returns None in that case, same convention
    as record.record_until_silence() returning empty audio)."""
    while True:
        if not settings.get("power_on") or is_interrupt_active():
            return None
        try:
            return _text_input_queue.get(timeout=poll_interval)
        except queue.Empty:
            continue


def _voice_list():
    return {"type": "voices", "voices": [{"value": k, "label": v} for k, v in VOICE_LABELS.items()]}


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
    await websocket.send(json.dumps(_voice_list()))
    await websocket.send(json.dumps({"type": "settings", **settings.get_all()}))
    # Without this, a client that connects AFTER a state broadcast already
    # fired (e.g. the Electron window is still spinning up its WebSocket
    # when the backend finishes loading and broadcasts "idle") would never
    # find out — broadcast() is fire-and-forget to whoever's connected
    # *at that instant*, and there's no guarantee another state change
    # happens later to correct it. This was the "stuck on Starting up..."
    # bug: the backend really was ready, but that specific "idle" message
    # had nowhere to go yet.
    if _last_state is not None:
        await websocket.send(json.dumps(_last_state))


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
    global _last_state
    _last_state = {"type": "state", "state": state, "user_text": user_text, "reply_text": reply_text}
    _broadcast_json(_last_state)


def broadcast_settings() -> None:
    _broadcast_json({"type": "settings", **settings.get_all()})


def broadcast_message(payload: dict) -> None:
    """Fire-and-forget send of an arbitrary typed message — for anything
    that isn't a state transition (broadcast()) or a settings snapshot
    (broadcast_settings()), e.g. the "console add" UI's database list and
    submit-result messages. `payload` must include its own "type" key."""
    _broadcast_json(payload)


def broadcast_amplitude(rms: float) -> None:
    """Fire-and-forget, called from tts.py's audio callback (a
    non-asyncio thread) once per output block during playback, so the
    frontend's speaking pulse can track Alani's actual output level
    instead of a synthetic rhythm."""
    _broadcast_json({"type": "amplitude", "value": rms})


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
