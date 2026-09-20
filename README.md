# Alani

A local voice assistant. Runs entirely on your own PC — wake word
detection, speech-to-text, a local LLM, and text-to-speech, all offline
except for a couple of free keyless APIs (weather) and triggering
[Alani-Bot](https://github.com/OrkusReOrca/Alani-Bot)'s GitHub Actions.

## Architecture

Two-stage, matching the actual constraint (near-zero idle footprint, a
capped VRAM budget when active):

```
[always-on, ~0% CPU]
wake word listener (openWakeWord)
        |  "Hey Alani"
        v
[spun up on demand]
record -> speech-to-text (faster-whisper)
       -> LLM + tool calling (Ollama)
       -> text-to-speech (Chatterbox) -> playback
```

An optional Electron + Three.js status widget (`frontend/`) shows what
Alani's doing — idle, listening, thinking, speaking, done — but the
backend runs identically whether or not it's open.

See `../alani-voice-methodology.txt` (outside this repo, never committed)
for the full research/decision log behind these choices.

## Setup

### Backend

```bash
cd Alani
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Requires:
- [Ollama](https://ollama.com) installed and running, with a model pulled:
  `ollama pull qwen3:8b` (default in `.env.example` — see that file to
  use a different model)
- An NVIDIA GPU for real-time performance (developed against an RTX 3060 Ti,
  8GB VRAM); CPU-only will work but be much slower

Run it:

```bash
cd src
python main.py
```

### Frontend (optional status widget)

```bash
cd frontend
npm install
npm start
```

Connects to the backend over `ws://localhost:8765` — run the backend
first (or just leave the widget open; it reconnects automatically).

## Current capabilities

Conversational only, for now:
- Wake word ("Hey Alani" once a custom model is trained — see
  `src/wake_word/listener.py` for the current fallback)
- Basic tools: roll dice, tell the time, check the weather, trigger an
  Alani-Bot GitHub Actions workflow
- Anything else: Alani says she can't do that yet, rather than guessing
  or making something up

## Adding tools

New capabilities go in `src/assistant/tools.py` — add the function, its
`TOOL_SCHEMAS` entry, and register it in `TOOL_FUNCTIONS`. The LLM decides
when to call it based on the schema's description.

## Cross-repo bridge

`src/assistant/github_bridge.py` shells out to the `gh` CLI (already
authenticated on this machine) to trigger workflows in Alani-Bot on
demand — e.g. "Alani, refresh the jam tracks now" instead of waiting for
its schedule. One-directional (local triggers cloud); the reverse isn't
implemented since this PC isn't always running.

## License

Copyright (c) 2026 OrkusReOrca. **All rights reserved.** The source is public
for viewing only; no permission is granted to use, copy, modify, or
redistribute it. See [LICENSE](LICENSE).
