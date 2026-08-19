"""Entrypoint. Run from src/: `python main.py`

Idle: wake_word.listener sits at near-zero CPU/RAM waiting for "Hey Alani"
(or the fallback wake word until a custom one is trained).
Active: on detection, runs a conversation session — repeated turns until
the user goes quiet (no speech heard in a turn), then drops back to idle.

The Electron UI (frontend/) is entirely optional — this runs the same
whether or not it's open; ui_bridge just broadcasts state to it if present.
"""


# IMPORTANT: torch must be imported before faster-whisper/ctranslate2.
# Both bundle their own (different-version) cudnn64_9.dll, and Windows
# only loads one copy of a same-named DLL per process — whichever loads
# first wins. Loading torch's first (its bundle is the more complete
# cuDNN 9 build) avoids a "Could not load symbol cudnnGetLibConfig"
# crash when Chatterbox later needs it. See methodology log for the
# full diagnosis.
import torch  # noqa: F401

from assistant import ui_bridge
from assistant.llm import Conversation
from assistant.pipeline import run_turn
from wake_word.listener import listen_for_wake_word


def on_wake():
    print("\n[woken up]")
    conversation = Conversation()
    while run_turn(conversation):
        pass  # keep taking turns until the user stops talking
    print("[back to idle]")
    ui_bridge.broadcast("done")


if __name__ == "__main__":
    ui_bridge.start()
    ui_bridge.broadcast("idle")
    listen_for_wake_word(on_wake)
