import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = REPO_ROOT / "models"

# LLM
OLLAMA_MODEL = os.environ.get("ALANI_OLLAMA_MODEL", "qwen3:8b")

# STT
WHISPER_MODEL_SIZE = os.environ.get("ALANI_WHISPER_MODEL", "small")
WHISPER_DEVICE = os.environ.get("ALANI_WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE_TYPE = os.environ.get("ALANI_WHISPER_COMPUTE_TYPE", "int8_float16")

# Wake word
CUSTOM_WAKE_WORD_PATH = MODELS_DIR / "hey_alani.onnx"
FALLBACK_WAKE_WORD = "hey_jarvis_v0.1"  # used until a custom "hey_alani" model is trained

# TTS voice cloning — named reference clips for Chatterbox to imitate. Paths
# live in .env (gitignored) rather than hardcoded here since they point to
# personal audio files outside the repo entirely. Add more by adding another
# ALANI_VOICE_<NAME>_PATH entry to .env and a matching line below (plus a
# label in VOICE_LABELS so it shows up in the UI's voice dropdown).
VOICES = {
    "VoiceSkyD": os.environ.get("ALANI_VOICE_SKYD_PATH"),
    "VoiceEuno": os.environ.get("ALANI_VOICE_EUNO_PATH"),
    "VoiceMatureDeep": os.environ.get("ALANI_VOICE_MATUREDEEP_PATH"),
    "VoiceMatureGentle": os.environ.get("ALANI_VOICE_MATUREGENTLE_PATH"),
}
VOICES = {name: Path(path) for name, path in VOICES.items() if path}

# "default" is a reserved sentinel (not a VOICES key) meaning Chatterbox's
# stock built-in voice, no cloning — see tts.py's _apply_voice().
VOICE_LABELS = {
    "default": "male default",
    "VoiceSkyD": "female monotone (SkyD)",
    "VoiceEuno": "female gentle (Eun)",
    "VoiceMatureDeep": "female mature deep",
    "VoiceMatureGentle": "female mature gentle",
}

# Legacy one-time env fallback: which voice to speak with before the user
# has ever picked one via the UI (settings.py seeds its persisted default
# from this). Once a choice is saved to settings.json, that always wins —
# ALANI_VOICE_NAME in .env only matters for a brand-new install.
ACTIVE_VOICE_NAME = os.environ.get("ALANI_VOICE_NAME") or "default"

# GitHub bridge
GITHUB_BOT_REPO = os.environ.get("ALANI_GITHUB_BOT_REPO", "OrkusReOrca/Alani-Bot")

# Alani-Bot Discord bridge — lets voice tools reach the always-on Discord
# bot for things that need its database (reminders for now), which lives
# only on the bot's own host disk, not reachable from this PC directly.
# See assistant/discord_bridge.py and Alani-Bot's src/features/db/voiceApi.js.
ALANI_BOT_API_URL = os.environ.get("ALANI_BOT_API_URL")  # e.g. http://<host-ip>:<port>
ALANI_BOT_API_SECRET = os.environ.get("ALANI_BOT_API_SECRET")

# Web search — Brave Search API (free tier, no credit card). Get a key at
# https://brave.com/search/api/.
BRAVE_SEARCH_API_KEY = os.environ.get("ALANI_BRAVE_SEARCH_API_KEY")
