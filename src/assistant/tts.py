"""Text-to-speech via Chatterbox-Turbo (`chatterbox.tts_turbo.ChatterboxTurboTTS`
— NOT `chatterbox.tts.ChatterboxTTS`, the standard/slower model; that was
this file's actual import for a while despite the docstring already
claiming Turbo, and is roughly ~6x the generation time on this GPU class
for no benefit). Uses a cloned voice per settings.get("voice_name") if
set to a config.VOICES key, otherwise Chatterbox's stock voice ("default").

Turbo's Conditionals aren't binary-compatible with the standard model's —
switching between them means every cached voice under models/voices/*.pt
needs regenerating (deleting the stale ones is enough; prepare_voice_cache
rebuilds them from the original reference clips automatically next launch).

Voice conditioning (`prepare_conditionals`) only needs to run ONCE per
reference clip, not per reply — it computes a speaker embedding/conditioning
state that Chatterbox caches on the model instance (`model.conds`) and reuses
automatically on every later `generate()` call that doesn't pass a new
`audio_prompt_path`. Passing `audio_prompt_path` to `generate()` on every
call (the naive approach) would silently re-run that conditioning step from
scratch each time — wasted GPU work on every single reply, for a clip that
never changes. So this happens once per voice — and even that one-time cost
is skipped on later app launches by caching the computed conditioning to
disk per named voice (Chatterbox's own Conditionals.save/.load, one .pt per
voice under models/voices/), keyed off the reference clip's mtime so
editing/replacing a clip transparently invalidates just that voice's cache.

Switching voices at runtime (via the UI's voice dropdown) re-applies this
same cached-conditioning swap on the next speak() call — see _apply_voice().
It's deliberately lazy (checked once per speak(), not on every settings
change) so a user cycling through the dropdown doesn't reload a voice on
every intermediate value; only the one they land on ever gets loaded.
"""

import threading

import numpy as np
import sounddevice as sd
from chatterbox.tts_turbo import ChatterboxTurboTTS, Conditionals

from . import settings, ui_bridge
from .config import MODELS_DIR, VOICES

_model = None
_active_voice_name = None  # which voice's conditioning is currently on _model.conds
_default_conds = None  # Chatterbox's stock voice, captured once at model load
VOICES_CACHE_DIR = MODELS_DIR / "voices"


def _cache_path(voice_name: str):
    return VOICES_CACHE_DIR / f"{voice_name}.pt"


def prepare_voice_cache(model: ChatterboxTurboTTS, voice_name: str, voice_path) -> None:
    """Compute (or reuse) a voice's conditioning and leave it cached on disk,
    without touching model.conds — used to pre-warm every known voice's
    cache regardless of which one is currently active.
    """
    cache_path = _cache_path(voice_name)
    if cache_path.exists() and cache_path.stat().st_mtime >= voice_path.stat().st_mtime:
        print(f"[tts] {voice_name} cache already up to date")
        return
    print(f"[tts] cloning voice {voice_name} from {voice_path.name}")
    model.prepare_conditionals(str(voice_path))
    VOICES_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    model.conds.save(cache_path)


def _apply_voice(model: ChatterboxTurboTTS, voice_name: str) -> None:
    global _active_voice_name
    if voice_name == _active_voice_name:
        return  # already loaded — the common case, keeps this a cheap no-op per reply

    if voice_name != "default":
        voice_path = VOICES.get(voice_name)
        if voice_path is None:
            print(f"[tts] unknown voice {voice_name!r}, falling back to default")
            voice_name = "default"

    if voice_name == "default":
        model.conds = _default_conds
    else:
        cache_path = _cache_path(voice_name)
        cache_fresh = cache_path.exists() and cache_path.stat().st_mtime >= voice_path.stat().st_mtime
        if not cache_fresh:
            prepare_voice_cache(model, voice_name, voice_path)
        print(f"[tts] switching to voice {voice_name}")
        model.conds = Conditionals.load(cache_path, map_location=model.device)

    _active_voice_name = voice_name


def _get_model():
    global _model, _default_conds
    if _model is None:
        _model = ChatterboxTurboTTS.from_pretrained(device="cuda")
        _default_conds = _model.conds
    _apply_voice(_model, settings.get("voice_name"))
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
        if not settings.get("power_on") or ui_bridge.is_interrupt_active():
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
