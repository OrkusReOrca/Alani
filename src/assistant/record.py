"""Simple energy-based voice recording: records from the mic until the
user stops talking (a period of quiet after speech was detected), or a
max duration is hit. No extra VAD dependency — good enough for a first
version; a proper VAD (e.g. webrtcvad/Silero) is a natural upgrade if this
proves too twitchy in practice.
"""

import numpy as np
import sounddevice as sd

from . import settings, ui_bridge

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)

SILENCE_RMS_THRESHOLD = 0.015
SILENCE_FRAMES_TO_STOP = int(1.0 * 1000 / FRAME_MS)  # ~1s of quiet ends the turn
MAX_DURATION_S = 15
MIN_SPEECH_FRAMES = 5  # ignore brief noise blips before real speech starts


def record_until_silence() -> np.ndarray:
    frames = []
    silence_run = 0
    speech_frames = 0
    heard_speech = False

    device = settings.get("input_device")
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=device) as stream:
        max_frames = int(MAX_DURATION_S * 1000 / FRAME_MS)
        for _ in range(max_frames):
            if not settings.get("power_on") or ui_bridge.is_interrupt_active():
                return np.array([], dtype="float32")  # instant abort, see main.py

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

    # Gate on the SAME signal that already decided when to stop recording
    # (heard_speech), rather than a second, independent absolute-RMS check
    # on the whole clip. An earlier version added a post-hoc overall-clip
    # RMS floor as an extra hallucination defense, but that averages in
    # up to a full second of trailing (and any leading) silence, which
    # dilutes real-but-short utterances below the floor — that caused a
    # real "never replies, silently returns to idle" bug. vad_filter +
    # no_speech_prob in stt.py are the real hallucination defense; this
    # check is just "did we actually detect speech at all".
    if not heard_speech or not frames:
        return np.array([], dtype="float32")

    return np.concatenate(frames)
