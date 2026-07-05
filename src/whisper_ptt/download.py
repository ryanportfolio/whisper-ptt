"""Explicit, user-initiated model download.

Offline-first invariant: nothing here runs on its own. It is reached only from
an explicit user action — the settings window's "Download" button or
scripts/fetch_model.py — mirroring the sanctioned network fetch that
``Config.allow_download`` permits. No code path arrives here silently.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .config import models_dir

log = logging.getLogger("whisper_ptt.download")

# Systran publishes CT2-converted faster-whisper models.
_REPOS = {
    "base.en": "Systran/faster-whisper-base.en",
    "small.en": "Systran/faster-whisper-small.en",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
}

# Approx on-disk size, shown in the UI so a click is an informed one.
MODEL_SIZE = {
    "base.en": "≈ 145 MB",
    "small.en": "≈ 480 MB",
    "base": "≈ 145 MB",
    "small": "≈ 480 MB",
}

KNOWN_MODELS = tuple(_REPOS)


def model_repo(name: str) -> str | None:
    """HuggingFace repo id for a model name, or None if unknown."""
    return _REPOS.get(name)


def download_model(name: str, dest_root: Path | None = None) -> Path:
    """Fetch a CT2 whisper model into the local store; return its directory.

    Writes to the canonical per-user store (``models_dir()``) by default — the
    first root ``Config.model_search_roots()`` checks — so the app resolves the
    model offline immediately afterward. Blocking and network-bound: call this
    off the UI thread. Raises ``ValueError`` for an unknown model name.
    """
    from huggingface_hub import snapshot_download  # heavy + network; import late

    repo = _REPOS.get(name)
    if repo is None:
        raise ValueError(f"unknown model {name!r}; choose from {sorted(_REPOS)}")

    root = Path(dest_root) if dest_root is not None else models_dir()
    dest = root / f"faster-whisper-{name}"
    dest.mkdir(parents=True, exist_ok=True)
    log.info("downloading %s -> %s", repo, dest)
    snapshot_download(
        repo_id=repo,
        local_dir=str(dest),
        allow_patterns=["*.bin", "*.json", "*.txt", "vocabulary*", "tokenizer*"],
    )
    log.info("model download done: %s", dest)
    return dest
