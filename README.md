# whisper-ptt

Local, offline **push-to-talk speech-to-text** for Windows. Tap a global
hotkey, speak, tap again. The transcript is pasted into whatever window is
focused and left on your clipboard. No cloud, no account, no network after the
one-time model download.

[![CI](https://github.com/Aoh1578/whisper-ptt/actions/workflows/ci.yml/badge.svg)](https://github.com/Aoh1578/whisper-ptt/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)
![Platform: Windows](https://img.shields.io/badge/Platform-Windows-0078D6.svg)

![The dictation flow: tap the hotkey, speak, tap again, and the transcript lands in the focused window](docs/demo.gif)

<sub>*Illustrative animation (drawn with the app's real tray icons) — regenerate with `scripts/make_demo_gif.py`.*</sub>

## What it is

A tiny system-tray app that turns your microphone into a global dictation
key. Hit the hotkey, talk, hit it again, and the words appear in your editor,
browser, chat box, or terminal. Everything runs on your own CPU with
[faster-whisper](https://github.com/SYSTRAN/faster-whisper). Once the model is
downloaded, the app never touches the network again.

## Features

- **Fully offline** after one model download. No accounts, no telemetry, no
  cloud calls.
- **Runs on any Windows machine's CPU** — no GPU, CUDA toolkit, or vendor
  drivers required; every dependency is a prebuilt wheel.
- **Global hotkey**, push-to-talk *or* toggle, via a low-level `pynput`
  keyboard hook — switchable from the tray without a restart.
- **System tray UI** with procedural idle / recording / transcribing / loading
  / error icons and a menu to switch mode, swap model, toggle settings, open
  the config, or quit. Tray changes are saved back to the config file.
- **Private-by-default logging**: the log file records lengths only — the words
  you dictate are never written to disk unless you opt in (`log_transcripts`,
  also togglable from the tray Settings menu).
- **Three output modes**: paste (clipboard + simulated `Ctrl+V`), type (Unicode
  `SendInput` fallback for apps that block paste), or clipboard-only.
- **Native-rate capture**, resampled to 16 kHz, so any working input device
  works without manual sample-rate juggling.
- **Offline-first model guard**: if the selected model isn't present locally the
  app refuses to start rather than silently reaching the network (opt in with
  `allow_download`).
- **Optional silent autostart** at login.

## CPU-only by design

Running on the CPU is a feature, not a fallback: it works on **any Windows
machine** — no GPU required, no CUDA toolkit, no vendor drivers, no
hardware lock-in. Every dependency installs as a prebuilt wheel, and
`base.en` int8 transcribes comfortably in real time for dictation on a
modern multicore desktop.

For the curious, GPU acceleration also isn't currently a realistic option
for non-NVIDIA hardware: CTranslate2 (the engine under faster-whisper) has
no Vulkan/DirectML/ROCm backend, and the prebuilt Whisper-Vulkan
alternatives ride whisper.cpp 1.8.x, which has a regression
([ggml-org/whisper.cpp#3455](https://github.com/ggml-org/whisper.cpp/issues/3455))
that silently falls back to CPU on AMD Vulkan. A real GPU opt-in (e.g. a
from-source `pywhispercpp` build pinned to whisper.cpp v1.7.6) is a
documented future option — not worth the fragility unless CPU latency
proves too slow for your use.

## Requirements

- **Windows** (the hotkey hook, paste/type injection, and autostart are
  Windows-specific).
- **Python 3.11.x** (pinned via `.python-version`; the deps dodge missing
  3.13/3.14 wheels for `ctranslate2` / `onnxruntime`).
- [**uv**](https://docs.astral.sh/uv/) for the environment and runner.
- A working input microphone.

## Install

From the project root:

```powershell
uv venv --python 3.11.15 .venv
uv sync --extra build                    # runtime deps + huggingface-hub (for the fetch step)
uv run python scripts\fetch_model.py     # one-time: bundles base.en (~75MB)
```

`uv sync` installs the exact pinned dependency set from `pyproject.toml`, so the
environment can't drift from the project metadata. The `build` extra adds
`huggingface-hub`, which `scripts\fetch_model.py` needs to download the model.
Prefer `uv pip install -e ".[build]"` if you want an editable install.

Every dependency installs as a prebuilt wheel. No C compiler, no CUDA toolkit.

The model is stored under `%LOCALAPPDATA%\whisper-ptt\models` (where
`fetch_model.py` writes it) and discovered automatically, whether you run from a
source checkout or an installed copy. The app is **offline by default**: if a
selected model isn't present locally it refuses to start and tells you to run
`fetch_model.py`, rather than silently downloading. Set `allow_download = true`
in the config to permit a one-time HuggingFace fetch.

## Run

```powershell
uv run whisper-ptt
# or: uv run python -m whisper_ptt
# or: .\scripts\run.ps1   (foreground, shows logs)
```

A microphone icon appears in the tray. **Tap the `` ` `` (backtick) key** to
start dictating, speak, **tap `` ` `` again** to stop. The text lands in the
focused window. (Default is toggle on the backtick key; while the app runs that
key is reserved for dictation and won't type a literal `` ` ``. Change the key
or mode from the tray menu — no restart needed — or in config.)

List your input devices: `uv run python -m whisper_ptt --list-devices`

### Autostart (optional)

```powershell
.\scripts\install-autostart.ps1          # run silently at login
.\scripts\install-autostart.ps1 -Remove  # undo
```

The shortcut runs at **normal (non-elevated) privilege**, so the global hotkey
will not fire while an elevated/admin window is focused (see Known limitations).

## Configuration

First run copies `config.example.toml` to
`%APPDATA%\whisper-ptt\config.toml`. Edit it (or use the tray **Open config**
menu) and restart. Mode, model, and settings changed from the tray menu are
written back to this file automatically (comments preserved). Key settings:

| Key | Default | Notes |
|---|---|---|
| `hotkey` | `` ` `` | global chord (`pynput` syntax); e.g. `f9`, `ctrl+alt+space`. Common choices are also pickable from the tray **Settings > Hotkey** menu |
| `mode` | `toggle` | `toggle` (tap/tap) or `ptt` (hold) |
| `suppress_hotkey` | `true` | swallow a single printable hotkey key while running |
| `model` | `base.en` | or `small.en` (more accurate, ~2x CPU) |
| `allow_download` | `false` | if a model isn't local, `false` refuses (offline); `true` permits a HuggingFace fetch |
| `max_capture_seconds` | `300` | safety cap; capture auto-stops so an abandoned recording can't grow RAM. `0` = no cap |
| `output_mode` | `paste` | `paste` \| `type` \| `clipboard-only` |
| `restore_clipboard` | `false` | transcript is left on the clipboard |
| `log_transcripts` | `false` | write dictated text to the log file; off = lengths only |
| `device_index` | default input | set to force a specific mic |
| `compute_type` | `int8` | `int8_float32` / `float32` for accuracy |
| `cpu_threads` | `0` (auto) | lower to keep the desktop responsive |

## Models

- **`base.en`** (default, ~75MB) is fast and comfortably real-time for
  dictation. **`small.en`** (~250MB, roughly 2x the CPU) is more accurate.
- Fetch either with `scripts\fetch_model.py` (append `small.en` to also fetch
  it). Models resolve in order from `%LOCALAPPDATA%\whisper-ptt\models`, then a
  `<repo>\models` fallback for source-run dev.
- **Offline invariant**: a missing model refuses launch by default. Set
  `allow_download = true` for a one-time (logged, not silent) HuggingFace fetch.
- `model` may also be an **absolute path** to a CTranslate2-converted model
  directory as an escape hatch.

## Known limitations (Windows)

- **Elevated windows:** a non-elevated app cannot hook keys for, or paste into,
  an elevated/admin foreground window (Task Manager, an elevated terminal). The
  hotkey is dead while such a window is focused. Run the app elevated if you
  need that coverage.
- **Paste-blocking apps:** some terminals/secure fields ignore synthetic
  `Ctrl+V`. Switch `output_mode = "type"`.
- **First transcript of a long clip** pegs CPU cores briefly (one-shot, fires on
  release). Fine for dictation, slower than a streaming/GPU design would be.

## Troubleshooting

**Check the log first.** The app writes a rotating log to
`%APPDATA%\whisper-ptt\whisper-ptt.log`. Under the console-less autostart path
(`pythonw.exe`) that log is the only place errors surface, so start there when
something misbehaves.

### No audio / mic not detected

Verify capture before anything else:

```powershell
uv run python -m whisper_ptt --test-capture   # records ~1.5s, reports level
uv run python -m whisper_ptt --list-devices
```

- **"NO AUDIO" / 0 samples**: no microphone is delivering data. On a desktop
  this usually means nothing is plugged into the mic jack, or the mic endpoint
  is *Not present / Unplugged* in **Settings -> System -> Sound -> Input**.
  Connect a mic, enable it, and set it as the **default recording device**. Once
  Windows marks it active, it appears under the MME/WASAPI host APIs and capture
  works.
- **Only WDM-KS devices listed** (and they don't deliver): symptom of the
  above. No shared-mode endpoint is active, so only raw kernel pins enumerate.
- **"SILENT" / near-zero level**: a device opened but is muted or is the wrong
  input. Unmute it, or pick the right one (`device_index` in config).

The app captures at the device's native rate and resamples to 16 kHz, so any
working input device is fine.

## CLI reference

```powershell
uv run python -m whisper_ptt --list-devices   # list input audio devices and exit
uv run python -m whisper_ptt --test-capture   # record ~1.5s from the resolved mic, report level, exit
uv run python -m whisper_ptt --version        # print version and exit
```

## Development and tests

The test suite is framework-free and needs no network:

```powershell
uv run python tests\test_model_resolution.py
uv run python tests\test_config_persist.py
```

The first exercises model resolution: the absolute-path escape hatch, data-dir
vs. repo-fallback discovery and their priority, and the two missing-model
outcomes (refuse by default vs. download-permitted). The second covers config
persistence: tray write-through preserving comments, and first-run seeding
with private logging defaults.

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs both suites on
`windows-latest`, plus an import smoke test, a clean `uv sync` of the pinned
wheels, and a check that the built wheel packages the example config.

### Project layout

```
src/whisper_ptt/
  __init__.py     package version
  __main__.py     enables `python -m whisper_ptt`
  app.py          entry point: wiring + worker state machine + CLI
  config.py       typed config, %APPDATA% TOML merge, model resolution
  hotkey.py       global chord hook (PTT key-up + toggle)
  audio.py        sounddevice capture -> in-memory float32
  transcriber.py  faster-whisper wrapper (load / warm_start / transcribe)
  output.py       clipboard + Ctrl+V paste / type / clipboard-only
  sendinput.py    ctypes SendInput Unicode typing fallback
  tray.py         pystray tray + menu
  icons.py        procedural tray-state icons
scripts/
  fetch_model.py        bundle the CT2 model (one-time)
  run.ps1               foreground launcher
  install-autostart.ps1 login autostart shortcut
  make_demo_gif.py      regenerate docs/demo.gif
tests/
  test_model_resolution.py  offline-first model-resolution tests
  test_config_persist.py    tray write-through + first-run seeding tests
```

## Privacy

whisper-ptt is offline by design. After the one-time model download it makes
**no network calls**, requires **no account**, and sends **no telemetry**. Your
audio is captured, transcribed on your own CPU, and discarded. Nothing leaves
the machine.

The rotating log file records only sample/character counts. The words you
dictate are never written to disk unless you explicitly enable
`log_transcripts` (off by default) — useful when debugging transcription
quality, off the rest of the time.

## License

[MIT](LICENSE) (c) 2026 Ryan Allen.

### Acknowledgements

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and the Systran
  CTranslate2-converted Whisper models
- [pynput](https://github.com/moses-palmer/pynput) (global hotkey)
- [pystray](https://github.com/moses-palmer/pystray) (system tray)
- [sounddevice](https://github.com/spatialaudio/python-sounddevice) (audio capture)
