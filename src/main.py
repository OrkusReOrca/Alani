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

import sys

# Windows' console defaults to a legacy codepage (cp1252 here), not UTF-8.
# Any print() of a character that codepage can't represent — an emoji in
# an LLM reply, say — raises UnicodeEncodeError. That happening inside
# pipeline.py's `print(f"Alani: {reply}")`, mid-turn, with nothing
# catching it, used to silently kill the session's background thread
# right after broadcasting "loading" and before ever broadcasting
# "speaking" — leaving the UI stuck showing the loading spinner forever
# (and the idle bar, which only exists in the "idle" state, never came
# back either — a second, uncaught symptom of the same crash). Qwen3
# turned out to reach for emoji far more often than Qwen2.5 did, which is
# what made this suddenly common. reconfigure()'d here, first thing, so
# it's in effect before any other module (including third-party ones)
# prints anything; errors="replace" means a still-unmappable character
# degrades to a placeholder glyph instead of ever crashing again.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# IMPORTANT: torch must be imported before faster-whisper/ctranslate2.
# Both bundle their own (different-version) cudnn64_9.dll, and Windows
# only loads one copy of a same-named DLL per process — whichever loads
# first wins. Loading torch's first (its bundle is the more complete
# cuDNN 9 build) avoids a "Could not load symbol cudnnGetLibConfig"
# crash when Chatterbox later needs it. See methodology log for the
# full diagnosis.
import torch  # noqa: F401

import threading

from assistant import discord_bridge, settings, ui_bridge
from assistant.llm import Conversation
from assistant.pipeline import run_turn
from wake_word.listener import listen_for_wake_word

# Hard circuit breaker: even with the hallucination guards in stt.py/
# record.py, a single wake session should never run forever. Caps the
# blast radius of any future bug the same way the Aug 2026 hallucination
# incident didn't have (see methodology log).
MAX_TURNS_PER_SESSION = 15

# Guards against two sessions running concurrently — e.g. the wake-word
# listener fires right as the user clicks the idle bar (force_wake), or
# they double-click it. Whichever gets here first runs; the other is a
# no-op. Real wake-word detection during an active session isn't possible
# anyway (the listener isn't running mid-session — see listen_for_wake_word),
# but the UI-triggered paths (force_wake, toggling reading_mode on) have no
# such guarantee on their own.
_session_lock = threading.Lock()
_session_active = False


def _run_session():
    global _session_active
    with _session_lock:
        if _session_active:
            return
        _session_active = True
    try:
        on_wake()
    finally:
        with _session_lock:
            _session_active = False


def on_wake():
    print("\n[woken up]")
    ui_bridge.clear_interrupt()  # wipe any stale force-idle click that arrived while idle
    conversation = Conversation()
    turns = 0
    while turns < MAX_TURNS_PER_SESSION and run_turn(conversation, is_first_turn=(turns == 0)):
        turns += 1
        if settings.get("sleep_mode"):
            print("[sleep mode] finishing this turn, then going idle")
            break
    if turns >= MAX_TURNS_PER_SESSION:
        print(f"[safety] hit the {MAX_TURNS_PER_SESSION}-turn cap for one session, ending it")
    print("[back to idle]")

    was_interrupted = ui_bridge.is_interrupt_active()
    ui_bridge.clear_interrupt()

    # Skip the "done" flourish if power was cut or the user force-idled —
    # both already jumped the UI straight to gray/idle the instant the
    # button was pressed (see ui_bridge/app.js), so a heart-then-idle beat
    # here would be a confusing extra step rather than the "instantly cut
    # off" those buttons promise.
    if settings.get("power_on") and not was_interrupted:
        ui_bridge.broadcast("done")


def _on_listener_ready():
    # Fires once the wake-word model has actually finished loading (a few
    # real seconds) — only then is "idle" (implying "already listening")
    # accurate. See ui_bridge/app.js's "starting" state.
    print("[wake word] ready")
    ui_bridge.broadcast("idle")


def _start_listener_thread():
    threading.Thread(
        target=listen_for_wake_word, args=(_run_session,), kwargs={"on_ready": _on_listener_ready}, daemon=True
    ).start()


@ui_bridge.on_command("set_volume")
def _on_set_volume(msg):
    settings.set("volume", float(msg["value"]))
    ui_bridge.broadcast_settings()


@ui_bridge.on_command("set_text_size")
def _on_set_text_size(msg):
    settings.set("text_size", int(msg["value"]))
    ui_bridge.broadcast_settings()


@ui_bridge.on_command("set_input_device")
def _on_set_input_device(msg):
    settings.set("input_device", msg["value"])
    ui_bridge.broadcast_settings()


@ui_bridge.on_command("set_output_device")
def _on_set_output_device(msg):
    settings.set("output_device", msg["value"])
    ui_bridge.broadcast_settings()


@ui_bridge.on_command("toggle_tts")
def _on_toggle_tts(msg):
    new_value = not settings.get("tts_enabled")
    settings.set("tts_enabled", new_value)
    print(f"[tts] {'on' if new_value else 'off'}")
    ui_bridge.broadcast_settings()


@ui_bridge.on_command("toggle_sleep")
def _on_toggle_sleep(msg):
    new_value = not settings.get("sleep_mode")
    settings.set("sleep_mode", new_value)
    print(f"[sleep mode] {'on' if new_value else 'off'}")
    ui_bridge.broadcast_settings()


@ui_bridge.on_command("set_voice")
def _on_set_voice(msg):
    settings.set("voice_name", msg["value"])
    print(f"[voice] switched to {msg['value']}")
    ui_bridge.broadcast_settings()


@ui_bridge.on_command("force_idle")
def _on_force_idle(msg):
    # The one condition that blocks this: a cloud/internet-dependent task
    # in progress (calendar, etc. — none exist yet, so this is always False
    # today; future cloud features should wrap themselves in
    # ui_bridge.set_cloud_task_active(True/False) so this stays correct).
    if ui_bridge.is_cloud_task_active():
        print("[force idle] ignored — a cloud-dependent task is in progress")
        return
    print("[force idle] user clicked the icon — cutting the current turn short")
    ui_bridge.request_interrupt()
    ui_bridge.broadcast("idle")


@ui_bridge.on_command("toggle_echo")
def _on_toggle_echo(msg):
    new_value = not settings.get("echo_mode")
    settings.set("echo_mode", new_value)
    print(f"[echo mode] {'on' if new_value else 'off'}")
    ui_bridge.broadcast_settings()


@ui_bridge.on_command("toggle_reading_mode")
def _on_toggle_reading_mode(msg):
    new_value = not settings.get("reading_mode")
    settings.set("reading_mode", new_value)
    print(f"[reading mode] {'on' if new_value else 'off'}")
    ui_bridge.broadcast_settings()
    # Clicking the toggle both flips the setting AND starts a turn right
    # now in whichever mode it just switched to — mirrors force_wake below,
    # not just a settings change.
    if settings.get("power_on"):
        threading.Thread(target=_run_session, daemon=True).start()


@ui_bridge.on_command("force_wake")
def _on_force_wake(msg):
    # Clicking the idle bar — starts a turn immediately, skipping the wake
    # word. Uses whatever reading_mode/echo_mode are currently set to;
    # this click only means "start now", not "start in voice mode".
    if settings.get("power_on"):
        print("[force wake] user clicked the bar")
        threading.Thread(target=_run_session, daemon=True).start()


@ui_bridge.on_command("text_input")
def _on_text_input(msg):
    ui_bridge.submit_text_input(msg["value"])


# ---------- "console add" — manual reminder/event entry, no LLM/TTS ----------
# Fully outside the turn-based session flow above (no recording, on_wake(),
# run_turn()) — a click-driven alternative for adding a reminder or event
# directly through a form. Mic pauses the instant this opens (see
# wake_word/listener.py checking ui_bridge.is_console_active()) so a wake
# word can't start a voice turn underneath an open form.


@ui_bridge.on_command("open_console")
def _on_open_console(msg):
    print("[console] opened")
    ui_bridge.set_console_active(True)
    ui_bridge.broadcast("console_add")

    # discord_bridge.list_databases() is a blocking network call — run it
    # off the websocket's own event-loop thread so a slow/unreachable bot
    # host doesn't stall other incoming commands meanwhile.
    def _fetch_databases():
        databases = discord_bridge.list_databases()
        ui_bridge.broadcast_message({"type": "databases", "databases": databases})

    threading.Thread(target=_fetch_databases, daemon=True).start()


@ui_bridge.on_command("close_console")
def _on_close_console(msg):
    print("[console] closed")
    ui_bridge.set_console_active(False)
    ui_bridge.broadcast("idle")


@ui_bridge.on_command("console_submit_reminder")
def _on_console_submit_reminder(msg):
    def _submit():
        success, message = discord_bridge.console_set_reminder(
            msg["text"],
            msg["remindAt"],
            database=msg.get("database", "main"),
            channel_id=msg.get("channelId") or None,
        )
        ui_bridge.broadcast_message({"type": "console_result", "kind": "reminder", "success": success, "message": message})

    threading.Thread(target=_submit, daemon=True).start()


@ui_bridge.on_command("console_submit_event")
def _on_console_submit_event(msg):
    def _submit():
        success, message = discord_bridge.console_add_event(
            msg["title"],
            msg["start"],
            end=msg.get("end") or None,
            all_day=bool(msg.get("allDay")),
            database=msg.get("database", "main"),
        )
        ui_bridge.broadcast_message({"type": "console_result", "kind": "event", "success": success, "message": message})

    threading.Thread(target=_submit, daemon=True).start()


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
    ui_bridge.broadcast("starting")

    if settings.get("power_on"):
        _start_listener_thread()
    else:
        print("[power] starting powered off (per saved settings)")
        ui_bridge.broadcast("idle")  # nothing else to wait for

    # Keep the process alive — the actual work happens in the listener
    # thread(s), which start/stop dynamically as power is toggled.
    threading.Event().wait()
