"""Broadcasts state to the Electron frontend over a local WebSocket, if
it's running. The backend works fine with no UI attached at all — this
is a one-way, best-effort broadcast, never something the pipeline depends
on or blocks meaningfully on.
"""

import asyncio
import json
import threading

import websockets

_clients = set()
_loop = None


async def _handler(websocket):
    _clients.add(websocket)
    try:
        await websocket.wait_closed()
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
    if _loop is None or not _clients:
        return
    payload = json.dumps({"state": state, "user_text": user_text, "reply_text": reply_text})

    async def _send():
        for client in list(_clients):
            try:
                await client.send(payload)
            except Exception:
                pass

    asyncio.run_coroutine_threadsafe(_send(), _loop)
