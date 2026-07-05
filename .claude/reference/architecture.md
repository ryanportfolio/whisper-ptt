# Architecture

> System flow + pointers into code. Terse. Populate via /recall save.

Push-to-talk loop: global hotkey → capture mic → transcribe offline → paste + clipboard.

| Concern | File |
|---|---|
| Entry / orchestration / CLI flags | `src/whisper_ptt/app.py`, `__main__.py` |
| Global hotkey listener | `src/whisper_ptt/hotkey.py` |
| Mic capture | `src/whisper_ptt/audio.py` |
| Offline transcription (faster-whisper) | `src/whisper_ptt/transcriber.py` |
| Paste into focused window + clipboard | `src/whisper_ptt/output.py`, `sendinput.py` |
| Tray icon | `src/whisper_ptt/tray.py`, `icons.py` |
| Config load / model resolution | `src/whisper_ptt/config.py` |
| Model fetch script | `scripts/fetch_model.py` |

Flow: tap hotkey (`hotkey.py`) → `audio.py` records until second tap → `transcriber.py` runs whisper on CPU → `output.py` pastes via `sendinput.py` and copies to clipboard. Offline-by-default: refuses to start if the model is absent unless `allow_download = true`.
