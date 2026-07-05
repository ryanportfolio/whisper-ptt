# Commands

> Build / dev / test / run commands for this project. `uv`-managed (Python 3.11).

| Task | Command |
|---|---|
| Install deps (exact pinned set) | `uv sync` |
| Install with model-fetch extra | `uv pip install -e ".[build]"` |
| One-time model download (~75MB base.en) | `uv run python scripts\fetch_model.py` |
| Run (tray) | `uv run whisper-ptt` |
| Run (module form) | `uv run python -m whisper_ptt` |
| Run foreground w/ logs | `.\scripts\run.ps1` |
| List input devices | `uv run python -m whisper_ptt --list-devices` |
| Test mic capture (~1.5s) | `uv run python -m whisper_ptt --test-capture` |
| Unit tests | `uv run pytest` |
| Autostart at login | `.\scripts\install-autostart.ps1` (`-Remove` to undo) |

Default hotkey: tap `` ` `` (backtick) to start/stop capture.
