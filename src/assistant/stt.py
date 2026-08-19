"""Speech-to-text via faster-whisper. Loaded on demand (not kept resident
alongside the LLM/TTS) to keep peak VRAM down — see methodology log for why.

Whisper is known to hallucinate text (often greeting-like phrases) on
near-silence/background-noise-only audio instead of returning nothing —
this caused a real runaway loop in testing (hallucination -> LLM reply ->
speak -> record silence -> hallucinate again). Two defenses here:
`vad_filter=True` (faster-whisper's own recommended fix, strips non-speech
before transcribing) and a `no_speech_prob` check as a second gate. See
methodology log for the incident.
"""

from faster_whisper import WhisperModel

from .config import WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE

NO_SPEECH_PROB_THRESHOLD = 0.6

_model = None


def _get_model():
    global _model
    if _model is None:
        _model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )
    return _model


def transcribe(audio_path_or_array) -> str:
    model = _get_model()
    segments, _info = model.transcribe(
        audio_path_or_array,
        language="en",
        vad_filter=True,
    )
    kept = [s.text.strip() for s in segments if s.no_speech_prob < NO_SPEECH_PROB_THRESHOLD]
    return " ".join(kept).strip()
