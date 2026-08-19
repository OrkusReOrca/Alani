"""Text-to-speech via Chatterbox-Turbo. Starts with Chatterbox's default
built-in voice (no reference clip yet — see methodology log). Swap to a
cloned voice later by passing `audio_prompt_path` to `generate()` once a
reference clip is available.
"""

import threading

import numpy as np
import sounddevice as sd
from chatterbox.tts import ChatterboxTTS

from . import settings, ui_bridge

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

    # Streamed via a callback (rather than one sd.play() with the gain
    # baked in up front) specifically so the volume slider has an actual
    # effect while Alani is mid-sentence — settings.get("volume") is read
    # fresh on every audio block, not once before playback starts.
    device = settings.get("output_device")
    position = 0
    done = threading.Event()

    def callback(outdata, frames, time_info, status):
        nonlocal position
        if not settings.get("power_on"):
            # Instant mid-speech cutoff — see main.py/methodology log.
            outdata[:, 0] = 0
            raise sd.CallbackStop()

        chunk = audio[position : position + frames]
        volume = float(settings.get("volume"))

        # Real output level (not the volume setting — that's loudness, this
        # is speech dynamics) so the frontend's "A" glyph pulse can track
        # what Alani is actually saying instead of a synthetic rhythm.
        if len(chunk):
            ui_bridge.broadcast_amplitude(float(np.sqrt(np.mean(chunk**2))))

        if len(chunk) < frames:
            outdata[: len(chunk), 0] = chunk * volume
            outdata[len(chunk) :, 0] = 0
            position += len(chunk)
            raise sd.CallbackStop()
        outdata[:, 0] = chunk * volume
        position += frames

    stream = sd.OutputStream(
        samplerate=model.sr, channels=1, device=device, callback=callback, finished_callback=done.set
    )
    with stream:
        done.wait()
