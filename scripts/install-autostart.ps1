# Create (or remove) a silent autostart shortcut for whisper-ptt.
#   .\install-autostart.ps1            # install
#   .\install-autostart.ps1 -Remove    # uninstall
# Uses pythonw.exe (no console window) from the project .venv.
param([switch]$Remove)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$startup = [Environment]::GetFolderPath("Startup")
$lnk = Join-Path $startup "whisper-ptt.lnk"

if ($Remove) {
    if (Test-Path $lnk) { Remove-Item $lnk; Write-Host "removed $lnk" }
    else { Write-Host "no autostart shortcut found" }
    return
}

$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) { throw "venv not found at $pythonw — run install first" }

$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($lnk)
$s.TargetPath = $pythonw
$s.Arguments = "-m whisper_ptt"
$s.WorkingDirectory = $root
$s.WindowStyle = 7  # minimized
$s.Description = "whisper-ptt local push-to-talk dictation"
$s.Save()
Write-Host "installed autostart shortcut -> $lnk"
Write-Host "NOTE: runs at normal (non-elevated) privilege; the global hotkey will"
Write-Host "      not fire while an elevated/admin window is focused."
