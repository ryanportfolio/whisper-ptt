# Deployment

> How this ships and runs.

- **No server, no pipeline.** Runs locally on the user's Windows 10/11 machine.
- Distribution: portable win64 build (see `Desktop\whisper-ptt-*-portable-win64` reference build) + optional login autostart via `scripts\install-autostart.ps1` (non-elevated, so the global hotkey works without admin).
- Model artifact: `base.en` (~75MB) fetched once to `%LOCALAPPDATA%\whisper-ptt\models`, discovered automatically. `models/` is gitignored — never commit it.
- Runtime config: `config.toml` (gitignored, local device indices/paths). `config.example.toml` stays committed as the template.
