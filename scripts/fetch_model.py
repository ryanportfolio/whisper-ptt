"""One-time helper: snapshot a CTranslate2 Whisper model into the local store.

By default writes to the canonical per-user store the app searches first,
%LOCALAPPDATA%\\whisper-ptt\\models, so the app is fully offline afterward
whether it runs from a source checkout or an installed wheel:

    uv run python scripts/fetch_model.py             # base.en
    uv run python scripts/fetch_model.py small.en    # also fetch small.en
    uv run python scripts/fetch_model.py --to-project base.en   # into ./models (dev)

The actual fetch lives in whisper_ptt.download (shared with the in-app
"Download" button); this is just the CLI around it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from whisper_ptt.download import KNOWN_MODELS, download_model  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(prog="fetch_model")
    ap.add_argument("models", nargs="*", default=["base.en"],
                    help=f"model names to fetch (default: base.en); "
                         f"choices: {', '.join(KNOWN_MODELS)}")
    ap.add_argument("--to-project", action="store_true",
                    help="write into the repo ./models (dev) instead of %%LOCALAPPDATA%%")
    args = ap.parse_args()

    # None -> the canonical %LOCALAPPDATA% store; --to-project -> ./models.
    root = (PROJECT_ROOT / "models") if args.to_project else None
    names = args.models or ["base.en"]
    for n in names:
        try:
            dest = download_model(n, dest_root=root)
        except ValueError as exc:
            raise SystemExit(str(exc))
        print(f"done: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
