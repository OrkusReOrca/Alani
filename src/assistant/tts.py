"""Text-to-speech via Chatterbox-Turbo. Starts with Chatterbox's default
built-in voice (no reference clip yet — see methodology log). Swap to a
cloned voice later by passing `audio_prompt_path` to `generate()` once a
reference clip is available.
"""

import numpy as np
import sounddevice as sd
from chatterbox.tts import ChatterboxTTS

from . import settings

_model = None


def _get_model():
    global _model
    if _model is None:
        _model = ChatterboxTTS.from_pretrained(device="cuda")
    return _model


def speak(text: str) -> None:
    if not text:
        return
    model = _get_model()
    wav = model.generate(text)
    audio = wav.squeeze().cpu().numpy().astype(np.float32)

    volume = float(settings.get("volume"))
    if volume != 1.0:
        audio = audio * volume

    device = settings.get("output_device")
    sd.play(audio, samplerate=model.sr, device=device)
    sd.wait()
