# Tech stack

> Non-default library choices and WHY, so future sessions don't "fix" deliberate picks.

- **Python pinned 3.11** (`.python-version`, `requires-python = ">=3.11,<3.12"`). Deliberate: dodges missing 3.13/3.14 prebuilt wheels for `ctranslate2` / `onnxruntime`. Do not bump without checking wheel availability.
- **`uv`** for env + dependency management. Every dep is a version-pinned prebuilt wheel — no C compiler, no CUDA. Keep it that way (CPU-only, offline-friendly install).
- **`faster-whisper` (ctranslate2 backend), CPU.** Offline speech-to-text. No GPU assumptions.
- **`sounddevice`** — mic capture. **`pynput`** — global hotkey. **`pyperclip`** — clipboard. **`pystray` + `Pillow`** — system-tray icon. **`SendInput`** (`sendinput.py`) — native Windows paste into the focused window.
- **Windows-only** by design (global hotkey + SendInput paste + tray). No cross-platform target.
