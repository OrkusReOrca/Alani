"""Entrypoint. Run from src/: `python main.py`

Idle: wake_word.listener sits at near-zero CPU/RAM waiting for "Hey Alani"
(or the fallback wake word until a custom one is trained).
Active: on detection, runs a conversation session — repeated turns until
the user goes quiet (no speech heard in a turn), then drops back to idle.

The Electron UI (frontend/) is entirely optional — this runs the same
whether or not it's open; ui_bridge just broadcasts state to it if present,
and relays the UI's device/volume/sleep/power controls back into
assistant.settings.
"""

# IMPORTANT: torch must be imported before faster-whisper/ctranslate2.
# Both bundle their own (different-version) cudnn64_9.dll, and Windows
# only loads one copy of a same-named DLL per process — whichever loads
# first wins. Loading torch's first (its bundle is the more complete
# cuDNN 9 build) avoids a "Could not load symbol cudnnGetLibConfig"
# crash when Chatterbox later needs it. See methodology log for the
# full diagnosis.
import torch  # noqa: F401

import threading

from assistant import settings, ui_bridge
from assistant.llm import Conversation
from assistant.pipeline import run_turn
from wake_word.listener import listen_for_wake_word

# Hard circuit breaker: even with the hallucination guards in stt.py/
# record.py, a single wake session should never run forever. Caps the
# blast radius of any future bug the same way the Aug 2026 hallucination
# incident didn't have (see methodology log).
MAX_TURNS_PER_SESSION = 15


def on_wake():
    print("\n[woken up]")
    conversation = Conversation()
    turns = 0
    while turns < MAX_TURNS_PER_SESSION and run_turn(conversation):
        turns += 1
    if turns >= MAX_TURNS_PER_SESSION:
        print(f"[safety] hit the {MAX_TURNS_PER_SESSION}-turn cap for one session, ending it")
    print("[back to idle]")
    ui_bridge.broadcast("done")


def _start_listener_thread():
    threading.Thread(target=listen_for_wake_word, args=(on_wake,), daemon=True).start()


@ui_bridge.on_command("set_volume")
def _on_set_volume(msg):
    settings.set("volume", float(msg["value"]))
    ui_bridge.broadcast_settings()


@ui_bridge.on_command("set_input_device")
def _on_set_input_device(msg):
    settings.set("input_device", msg["value"])
    ui_bridge.broadcast_settings()


@ui_bridge.on_command("set_output_device")
def _on_set_output_device(msg):
    settings.set("output_device", msg["value"])
    ui_bridge.broadcast_settings()


@ui_bridge.on_command("toggle_sleep")
def _on_toggle_sleep(msg):
    new_value = not settings.get("sleep_mode")
    settings.set("sleep_mode", new_value)
    print(f"[sleep mode] {'on' if new_value else 'off'}")
    ui_bridge.broadcast_settings()


@ui_bridge.on_command("toggle_power")
def _on_toggle_power(msg):
    new_value = not settings.get("power_on")
    settings.set("power_on", new_value)
    print(f"[power] {'on' if new_value else 'off'}")
    ui_bridge.broadcast_settings()
    if new_value:
        _start_listener_thread()


if __name__ == "__main__":
    ui_bridge.start()
    ui_bridge.broadcast("idle")

    if settings.get("power_on"):
        _start_listener_thread()
    else:
        print("[power] starting powered off (per saved settings)")

    # Keep the process alive — the actual work happens in the listener
    # thread(s), which start/stop dynamically as power is toggled.
    threading.Event().wait()
