"""Orchestrates one wake-up: record -> transcribe -> think -> speak.
Conversation history persists across turns within a single wake-up
session (see main.py for how sessions end).

Power-off is checked at every stage boundary (record.py and tts.py also
check it mid-stream, for a genuinely instant cutoff rather than "instant
except while actually recording/speaking" — see methodology log). The one
gap: Chatterbox's generate() call itself (turning text into audio, before
playback starts) isn't interruptible mid-computation — a power-off press
during that specific window finishes generating before the callback-level
check in tts.py can stop it. Accepted as a reasonable limitation rather
than adding real complexity (cancellable GPU work) for a sub-second window.
"""

import time

from . import record, settings, stt, tts, ui_bridge
from .end_phrases import is_end_phrase
from .llm import Conversation

READ_CHARS_PER_SEC = 18  # rough comfortable reading pace, for the tts_enabled=False pause
MIN_READ_PAUSE_S = 1.2
MAX_READ_PAUSE_S = 8.0


def _pace_reading(text: str) -> None:
    """Stands in for the time TTS playback would normally take, so
    skipping audio doesn't just flash the reply and move straight on to
    the next turn. Broken into small steps (rather than one time.sleep())
    so power-off still cuts in fast instead of waiting out the whole
    pause."""
    remaining = min(MAX_READ_PAUSE_S, max(MIN_READ_PAUSE_S, len(text) / READ_CHARS_PER_SEC))
    step = 0.1
    while remaining > 0 and settings.get("power_on"):
        time.sleep(step)
        remaining -= step


def run_turn(conversation: Conversation) -> bool:
    """Records and handles one user utterance. Returns False if the
    session should end (nothing was said, the user signaled they're done,
    or power was turned off mid-turn), True to keep listening."""
    print("[listening]")
    ui_bridge.broadcast("listening")
    audio = record.record_until_silence()
    if not settings.get("power_on") or audio.size == 0:
        return False

    print("[transcribing]")
    user_text = stt.transcribe(audio)
    if not settings.get("power_on") or not user_text:
        return False
    print(f"You said: {user_text}")
    ui_bridge.broadcast("listening", user_text=user_text)

    print("[thinking]")
    ui_bridge.broadcast("loading", user_text=user_text)
    reply = conversation.send(user_text)
    if not settings.get("power_on"):
        return False
    print(f"Alani: {reply}")

    print("[speaking]")
    ui_bridge.broadcast("speaking", user_text=user_text, reply_text=reply)
    # Read fresh right here (not cached from earlier in the turn) so a
    # mid-conversation toggle never interrupts audio already playing from
    # a previous turn — it just takes effect starting the next one.
    if settings.get("tts_enabled"):
        tts.speak(reply)
    else:
        _pace_reading(reply)

    if is_end_phrase(user_text):
        print("[end phrase detected] wrapping up this session")
        return False

    return settings.get("power_on")
