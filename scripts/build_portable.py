"""Build the portable Windows app: PyInstaller onedir + bundled model, zipped.

    uv run --with pyinstaller python scripts/build_portable.py [--no-zip]

Produces:
    dist/whisper-ptt/                            self-contained app folder
    dist/whisper-ptt-<ver>-portable-win64.zip    click-and-go release asset

The base.en model is bundled next to the exe when present (repo ./models
first, then %LOCALAPPDATA%\\whisper-ptt\\models) so the zip dictates offline
out of the box; fetch it first with scripts/fetch_model.py --to-project.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from whisper_ptt import __version__  # noqa: E402
from whisper_ptt.icons import make_icon  # noqa: E402

DIST = ROOT / "dist"
APP_DIR = DIST / "whisper-ptt"
BUILD = ROOT / "build"

PORTABLE_README = f"""whisper-ptt {__version__} (portable)
=====================================

1. Double-click whisper-ptt.exe — a microphone icon appears in the
   system tray (check the taskbar overflow arrow if you don't see it).
2. Tap ` (backtick) to start dictating, speak, tap ` again.
   The text is pasted into whatever window has focus.

Right-click the tray icon to change the hotkey, mode, model, or settings.

Config:  %APPDATA%\\whisper-ptt\\config.toml
Log:     %APPDATA%\\whisper-ptt\\whisper-ptt.log

Windows SmartScreen may warn on first run because the exe is unsigned:
choose "More info" -> "Run anyway".

Everything runs locally on your CPU. The app makes no network calls.
Project: https://github.com/ryanportfolio/whisper-ptt
"""


def _make_ico() -> Path:
    BUILD.mkdir(exist_ok=True)
    ico = BUILD / "whisper-ptt.ico"
    from PIL import Image
    img = make_icon("idle").resize((256, 256), Image.LANCZOS)
    img.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])
    return ico


def _run_pyinstaller(ico: Path) -> None:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed",
        "--name", "whisper-ptt",
        "--icon", str(ico),
        "--paths", str(ROOT / "src"),
        "--specpath", str(BUILD),
        "--workpath", str(BUILD / "pyinstaller"),
        "--distpath", str(DIST),
        # faster-whisper ships the silero VAD onnx as package data; ctranslate2
        # ships its DLLs. collect-all is the reliable way to get both.
        "--collect-all", "faster_whisper",
        "--collect-all", "ctranslate2",
        "--collect-binaries", "onnxruntime",
        # In-app model download (settings window "Download") needs huggingface_hub's
        # lazily imported submodules and a TLS cert bundle inside the frozen exe.
        "--collect-all", "huggingface_hub",
        "--collect-data", "certifi",
        # Backends these libs load dynamically (invisible to import analysis).
        "--hidden-import", "pystray._win32",
        "--hidden-import", "pynput.keyboard._win32",
        "--hidden-import", "pynput.mouse._win32",
        # First-run config seeding reads this via importlib.resources.
        "--add-data", f"{ROOT / 'config.example.toml'}{os.pathsep}whisper_ptt",
        str(ROOT / "packaging" / "entry.py"),
    ]
    subprocess.run(cmd, check=True)


def _bundle_model() -> bool:
    """Copy base.en next to the exe; returns False if not found locally."""
    name = "faster-whisper-base.en"
    local = (os.environ.get("LOCALAPPDATA")
             or os.environ.get("APPDATA") or str(Path.home()))
    for src in (ROOT / "models" / name,
                Path(local) / "whisper-ptt" / "models" / name):
        if src.exists():
            shutil.copytree(src, APP_DIR / "models" / name, dirs_exist_ok=True)
            print(f"bundled model: {src}")
            return True
    print("WARNING: base.en not found locally; zip will NOT be click-and-go. "
          "Run: python scripts/fetch_model.py --to-project base.en")
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-zip", action="store_true",
                    help="build dist/whisper-ptt/ but skip the zip")
    args = ap.parse_args()

    ico = _make_ico()
    _run_pyinstaller(ico)
    _bundle_model()
    (APP_DIR / "README.txt").write_text(PORTABLE_README, encoding="utf-8")

    if not args.no_zip:
        base = DIST / f"whisper-ptt-{__version__}-portable-win64"
        print("zipping (this takes a minute)...")
        out = shutil.make_archive(str(base), "zip",
                                  root_dir=DIST, base_dir="whisper-ptt")
        print(f"wrote {out} ({Path(out).stat().st_size / 1_048_576:.0f} MB)")
    print(f"portable app: {APP_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
