"""Always-on wake word listener. Designed to be the ONLY thing resident
in memory when idle — openWakeWord's models are tiny (a few hundred KB
total) and this loop is near-zero CPU between frames.

Until a custom "Hey Alani" model is trained (see methodology log —
openwakeword.com/train), this falls back to the bundled "hey_jarvis"
model so the pipeline is runnable end-to-end today. Drop a trained
hey_alani.onnx into models/ to switch over automatically.

Supports two control states, both driven by assistant.settings (which the
UI's Z/power buttons write to):
- sleep_mode: the mic stream is closed entirely (not just ignored) — no
  audio capture happening at all, near-zero CPU/GPU, and a clearer privacy
  story than "still recording but discarding it". Reopens automatically
  once sleep_mode clears.
- power_on: exits this function entirely when false; main.py starts a
  fresh thread when power comes back on.
"""

import time

import numpy as np
import openwakeword
import sounddevice as sd
from openwakeword.model import Model

from assistant import settings
from assistant.config import CUSTOM_WAKE_WORD_PATH, FALLBACK_WAKE_WORD

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 1280  # 80ms at 16kHz — openWakeWord's expected frame size
DETECTION_THRESHOLD = 0.5
SLEEP_POLL_S = 0.3


def _load_model():
    # tflite_runtime isn't readily pip-installable on Windows, so force the
    # ONNX inference path explicitly (openWakeWord supports both, but its
    # bundled pretrained models default to tflite if a framework isn't
    # named) and make sure the ONNX weights are actually downloaded.
    openwakeword.utils.download_models()

    if CUSTOM_WAKE_WORD_PATH.exists():
        print(f"[wake word] using custom model: {CUSTOM_WAKE_WORD_PATH.name}")
        return Model(wakeword_models=[str(CUSTOM_WAKE_WORD_PATH)], inference_framework="onnx")
    print(
        f"[wake word] no custom 'hey_alani' model found — falling back to "
        f"'{FALLBACK_WAKE_WORD}' for now. Train a real one at "
        f"openwakeword.com/train and drop it at {CUSTOM_WAKE_WORD_PATH}"
    )
    return Model(wakeword_models=[FALLBACK_WAKE_WORD], inference_framework="onnx")


def listen_for_wake_word(on_detected, on_ready=None) -> None:
    """Runs until settings.power_on becomes False. `on_ready`, if given,
    fires once right after the (slow, few-second) model load finishes —
    lets main.py tell the UI "actually listening now" instead of claiming
    it the instant the process starts."""
    model = _load_model()
    wakeword_name = list(model.models.keys())[0]
    if on_ready:
        on_ready()

    while settings.get("power_on"):
        if settings.get("sleep_mode"):
            time.sleep(SLEEP_POLL_S)
            continue

        device = settings.get("input_device")
        print("[wake word] listening...")
        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", device=device) as stream:
                while settings.get("power_on") and not settings.get("sleep_mode"):
                    chunk, _overflowed = stream.read(CHUNK_SAMPLES)
                    audio = chunk[:, 0].astype(np.int16)
                    prediction = model.predict(audio)

                    if prediction[wakeword_name] > DETECTION_THRESHOLD:
                        model.reset()
                        on_detected()
                        if not (settings.get("power_on") and not settings.get("sleep_mode")):
                            break
                        print("[wake word] listening...")
        except Exception as e:
            print(f"[wake word] stream error, retrying: {e}")
            time.sleep(1)

    print("[wake word] powered off")
