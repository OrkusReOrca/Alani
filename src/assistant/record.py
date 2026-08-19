"""Simple energy-based voice recording: records from the mic until the
user stops talking (a period of quiet after speech was detected), or a
max duration is hit. No extra VAD dependency — good enough for a first
version; a proper VAD (e.g. webrtcvad/Silero) is a natural upgrade if this
proves too twitchy in practice.
"""

import numpy as np
import sounddevice as sd

from . import settings

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)

SILENCE_RMS_THRESHOLD = 0.02
SILENCE_FRAMES_TO_STOP = int(1.0 * 1000 / FRAME_MS)  # ~1s of quiet ends the turn
MAX_DURATION_S = 15
MIN_SPEECH_FRAMES = 8  # ignore brief noise blips before real speech starts

# Overall-clip RMS floor: even if the frame-by-frame gate above let
# something through (e.g. a brief ambient noise spike), a genuinely quiet
# clip shouldn't get sent to Whisper at all — this is what was causing the
# hallucination-loop incident (see stt.py / methodology log).
CLIP_RMS_FLOOR = 0.015


def record_until_silence() -> np.ndarray:
    frames = []
    silence_run = 0
    speech_frames = 0
    heard_speech = False

    device = settings.get("input_device")
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=device) as stream:
        max_frames = int(MAX_DURATION_S * 1000 / FRAME_MS)
        for _ in range(max_frames):
            chunk, _overflowed = stream.read(FRAME_SAMPLES)
            chunk = chunk[:, 0]
            frames.append(chunk)

            rms = float(np.sqrt(np.mean(chunk**2)))
            if rms > SILENCE_RMS_THRESHOLD:
                speech_frames += 1
                silence_run = 0
                if speech_frames >= MIN_SPEECH_FRAMES:
                    heard_speech = True
            else:
                silence_run += 1

            if heard_speech and silence_run >= SILENCE_FRAMES_TO_STOP:
                break

    if not frames:
        return np.array([], dtype="float32")

    audio = np.concatenate(frames)
    clip_rms = float(np.sqrt(np.mean(audio**2)))
    if clip_rms < CLIP_RMS_FLOOR:
        return np.array([], dtype="float32")
    return audio
