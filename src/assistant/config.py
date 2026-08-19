import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = REPO_ROOT / "models"

# LLM
OLLAMA_MODEL = os.environ.get("ALANI_OLLAMA_MODEL", "qwen2.5:7b-instruct")

# STT
WHISPER_MODEL_SIZE = os.environ.get("ALANI_WHISPER_MODEL", "small")
WHISPER_DEVICE = os.environ.get("ALANI_WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE_TYPE = os.environ.get("ALANI_WHISPER_COMPUTE_TYPE", "int8_float16")

# Wake word
CUSTOM_WAKE_WORD_PATH = MODELS_DIR / "hey_alani.onnx"
FALLBACK_WAKE_WORD = "hey_jarvis_v0.1"  # used until a custom "hey_alani" model is trained

# GitHub bridge
GITHUB_BOT_REPO = os.environ.get("ALANI_GITHUB_BOT_REPO", "OrkusReOrca/Alani-Bot")
