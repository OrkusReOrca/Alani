"""Speech-to-text via faster-whisper. Loaded on demand (not kept resident
alongside the LLM/TTS) to keep peak VRAM down — see methodology log for why.
"""

from faster_whisper import WhisperModel

from .config import WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE

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
    segments, _info = model.transcribe(audio_path_or_array, language="en")
    return " ".join(segment.text.strip() for segment in segments).strip()
