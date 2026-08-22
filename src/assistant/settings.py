"""Live, persisted settings shared between the backend and the Electron
UI. The UI sends change requests over the websocket (see ui_bridge.py);
this module is the single source of truth both sides read from — nothing
here is cached at import time, so a change takes effect on the very next
use (next turn's recording, next TTS playback, next wake-word loop tick).
"""

import json
import threading
from pathlib import Path

from .config import ACTIVE_VOICE_NAME, REPO_ROOT

SETTINGS_PATH = REPO_ROOT / "data" / "settings.json"

DEFAULTS = {
    "input_device": None,  # None = system default
    "output_device": None,  # None = system default
    "volume": 1.0,  # 0.0 - 1.5
    "sleep_mode": False,  # True: not listening, near-zero CPU/GPU, still running
    "power_on": True,  # False: wake-word listener fully stopped
    "text_size": 13,  # px, conversation transcript font size
    "tts_enabled": True,  # False: skip speaking replies aloud, text-only
    "voice_name": ACTIVE_VOICE_NAME,  # "default" or a config.VOICES key — see tts.py
    "reading_mode": False,  # True: turns wait for typed text instead of recording audio
    "echo_mode": False,  # True: skip the LLM, reply is just whatever the user said
}

_lock = threading.Lock()
_settings = None


def _load():
    if not SETTINGS_PATH.exists():
        return dict(DEFAULTS)
    try:
        with open(SETTINGS_PATH, "r") as f:
            data = json.load(f)
        return {**DEFAULTS, **data}
    except Exception:
        return dict(DEFAULTS)


def _save():
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(_settings, f, indent=2)


def get_all() -> dict:
    global _settings
    with _lock:
        if _settings is None:
            _settings = _load()
        return dict(_settings)


def get(key: str):
    return get_all().get(key, DEFAULTS.get(key))


def set(key: str, value) -> dict:
    global _settings
    with _lock:
        if _settings is None:
            _settings = _load()
        _settings[key] = value
        _save()
        return dict(_settings)
