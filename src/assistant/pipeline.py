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

The UI's "force idle" click (top-right icon) uses the exact same checks,
via ui_bridge.is_interrupt_active() — same instant-cutoff points, same
non-interruptible-mid-call gap. It's a separate flag from power_on because
it doesn't stop the wake-word listener, just the current turn; see
main.py's on_command("force_idle") and on_wake().

Two settings change what a turn actually does, checked fresh at the top
of each one (not cached per-session) so toggling mid-conversation takes
effect starting the very next turn:
  - reading_mode: waits for typed text (ui_bridge.wait_for_text_input())
    instead of recording+transcribing audio. Everything after that point
    (thinking, speaking) is unchanged — only the input step differs.
  - echo_mode: skips conversation.send() entirely — the reply is just
    whatever the user said, not added to conversation history either
    (it's a mic/TTS mirror, not a real exchange).
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
    while remaining > 0 and settings.get("power_on") and not ui_bridge.is_interrupt_active():
        time.sleep(step)
        remaining -= step


def run_turn(conversation: Conversation, is_first_turn: bool = False) -> bool:
    """Records and handles one user utterance. Returns False if the
    session should end (nothing was said, the user signaled they're done,
    or power was turned off mid-turn), True to keep listening.

    is_first_turn: the turn immediately after waking up. An end phrase
    here skips the LLM/TTS entirely and goes straight back to idle — an
    accidental wake (false-positive wake word) or an immediate change of
    mind ("stop", "nevermind" right after waking) shouldn't cost a full
    LLM round-trip and a spoken reply just to say goodbye. Later turns
    are a real conversation already in progress, so those still get the
    normal reply-then-check treatment further down."""
    reading = settings.get("reading_mode")

    if reading:
        print("[reading]")
        ui_bridge.broadcast("reading")
        user_text = ui_bridge.wait_for_text_input()
        if not settings.get("power_on") or ui_bridge.is_interrupt_active() or not user_text:
            return False
    else:
        print("[listening]")
        ui_bridge.broadcast("listening")
        audio = record.record_until_silence()
        if not settings.get("power_on") or ui_bridge.is_interrupt_active() or audio.size == 0:
            return False

        print("[transcribing]")
        user_text = stt.transcribe(audio)
        if not settings.get("power_on") or ui_bridge.is_interrupt_active() or not user_text:
            return False

    print(f"You said: {user_text}")
    ui_bridge.broadcast("listening", user_text=user_text)

    if is_first_turn and is_end_phrase(user_text):
        print("[end phrase on first turn] skipping LLM/TTS, straight back to idle")
        return False

    print("[thinking]")
    ui_bridge.broadcast("loading", user_text=user_text)
    if settings.get("echo_mode"):
        reply = user_text
    else:
        reply = conversation.send(user_text)
    if not settings.get("power_on") or ui_bridge.is_interrupt_active():
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

    # should_end is always False in echo_mode (conversation.send() never
    # ran, so no tool could have set it) — is_end_phrase(user_text) still
    # applies there regardless, same as normal.
    if is_end_phrase(user_text) or conversation.should_end:
        reason = "end phrase" if is_end_phrase(user_text) else "end_conversation tool"
        print(f"[{reason} detected] wrapping up this session")
        return False

    return settings.get("power_on") and not ui_bridge.is_interrupt_active()
