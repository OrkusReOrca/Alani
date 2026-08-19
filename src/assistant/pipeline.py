"""Orchestrates one wake-up: record -> transcribe -> think -> speak.
Conversation history persists across turns within a single wake-up
session (see main.py for how sessions end).
"""

from . import record, stt, tts, ui_bridge
from .llm import Conversation


def run_turn(conversation: Conversation) -> bool:
    """Records and handles one user utterance. Returns False if nothing
    was actually said (so the caller can fall back to idle), True otherwise."""
    print("[listening]")
    ui_bridge.broadcast("listening")
    audio = record.record_until_silence()
    if audio.size == 0:
        return False

    print("[transcribing]")
    user_text = stt.transcribe(audio)
    if not user_text:
        return False
    print(f"You said: {user_text}")
    ui_bridge.broadcast("listening", user_text=user_text)

    print("[thinking]")
    ui_bridge.broadcast("loading", user_text=user_text)
    reply = conversation.send(user_text)
    print(f"Alani: {reply}")

    print("[speaking]")
    ui_bridge.broadcast("speaking", user_text=user_text, reply_text=reply)
    tts.speak(reply)
    return True
