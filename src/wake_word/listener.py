"""Always-on wake word listener. Designed to be the ONLY thing resident
in memory when idle — openWakeWord's models are tiny (a few hundred KB
total) and this loop is near-zero CPU between frames.

Until a custom "Hey Alani" model is trained (see methodology log —
openwakeword.com/train), this falls back to the bundled "hey_jarvis"
model so the pipeline is runnable end-to-end today. Drop a trained
hey_alani.onnx into models/ to switch over automatically.
"""

import numpy as np
import openwakeword
import sounddevice as sd
from openwakeword.model import Model

from assistant.config import CUSTOM_WAKE_WORD_PATH, FALLBACK_WAKE_WORD

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 1280  # 80ms at 16kHz — openWakeWord's expected frame size
DETECTION_THRESHOLD = 0.5


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


def listen_for_wake_word(on_detected) -> None:
    """Blocks forever, calling on_detected() each time the wake word fires."""
    model = _load_model()
    wakeword_name = list(model.models.keys())[0]

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
        print("[wake word] listening...")
        while True:
            chunk, _overflowed = stream.read(CHUNK_SAMPLES)
            audio = chunk[:, 0].astype(np.int16)
            prediction = model.predict(audio)

            if prediction[wakeword_name] > DETECTION_THRESHOLD:
                model.reset()
                on_detected()
                print("[wake word] listening...")
