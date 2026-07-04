# Launch whisper-ptt in the foreground (shows logs). Ctrl+C to stop.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
uv run --project $root whisper-ptt
