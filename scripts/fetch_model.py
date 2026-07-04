"""One-time helper: snapshot a CTranslate2 Whisper model into the local store.

By default writes to the canonical per-user store the app searches first,
%LOCALAPPDATA%\\whisper-ptt\\models, so the app is fully offline afterward
whether it runs from a source checkout or an installed wheel:

    uv run python scripts/fetch_model.py             # base.en
    uv run python scripts/fetch_model.py small.en    # also fetch small.en
    uv run python scripts/fetch_model.py --to-project base.en   # into ./models (dev)
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

# Systran publishes CT2-converted faster-whisper models.
_REPOS = {
    "base.en": "Systran/faster-whisper-base.en",
    "small.en": "Systran/faster-whisper-small.en",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
}

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _data_models_dir() -> Path:
    """Canonical per-user model store (mirrors whisper_ptt.config.models_dir)."""
    base = (os.environ.get("LOCALAPPDATA")
            or os.environ.get("APPDATA")
            or str(Path.home()))
    return Path(base) / "whisper-ptt" / "models"


def fetch(name: str, root: Path) -> Path:
    from huggingface_hub import snapshot_download

    repo = _REPOS.get(name)
    if repo is None:
        raise SystemExit(f"unknown model {name!r}; choose from {sorted(_REPOS)}")

    dest = root / f"faster-whisper-{name}"
    dest.mkdir(parents=True, exist_ok=True)
    print(f"downloading {repo} -> {dest}")
    snapshot_download(
        repo_id=repo,
        local_dir=str(dest),
        allow_patterns=["*.bin", "*.json", "*.txt", "vocabulary*", "tokenizer*"],
    )
    print(f"done: {dest}")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(prog="fetch_model")
    ap.add_argument("models", nargs="*", default=["base.en"],
                    help="model names to fetch (default: base.en)")
    ap.add_argument("--to-project", action="store_true",
                    help="write into the repo ./models (dev) instead of %%LOCALAPPDATA%%")
    args = ap.parse_args()

    root = (PROJECT_ROOT / "models") if args.to_project else _data_models_dir()
    names = args.models or ["base.en"]
    for n in names:
        fetch(n, root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
