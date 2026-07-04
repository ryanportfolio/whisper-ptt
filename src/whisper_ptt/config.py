"""Configuration: typed defaults merged over a user TOML at %APPDATA%\\whisper-ptt."""

from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

# src/whisper_ptt/config.py -> parents[2] == project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_CONFIG = PROJECT_ROOT / "config.example.toml"


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "whisper-ptt"


def config_path() -> Path:
    return config_dir() / "config.toml"


def data_dir() -> Path:
    """Per-user store for large local assets (models).

    LOCALAPPDATA, not APPDATA: models are big binaries that must not roam. This
    location is stable whether the app runs from a source checkout or an
    installed wheel — the model resolution never depends on PROJECT_ROOT.
    """
    base = (os.environ.get("LOCALAPPDATA")
            or os.environ.get("APPDATA")
            or str(Path.home()))
    return Path(base) / "whisper-ptt"


def models_dir() -> Path:
    """Canonical directory holding faster-whisper-<name> model folders."""
    return data_dir() / "models"


class ModelNotFound(Exception):
    """Model is not available locally and downloads are not permitted.

    Offline-first is a hard invariant: no code path silently reaches the
    network. When the model can't be resolved locally and allow_download is
    false, resolution raises this instead of falling back to a HuggingFace
    download.
    """

    def __init__(self, name: str, searched: list[Path]):
        self.name = name
        self.searched = searched
        where = "\n  ".join(str(p) for p in searched) or "(none)"
        super().__init__(
            f"model {name!r} not found locally and allow_download is false.\n"
            f"searched:\n  {where}\n"
            f"fetch it once with: python scripts/fetch_model.py {name}\n"
            f"(or set allow_download = true in the config to permit a network fetch)"
        )


@dataclass
class Config:
    # Hotkey
    hotkey: str = "`"
    mode: str = "toggle"  # "ptt" | "toggle"
    debounce_ms: int = 50
    suppress_hotkey: bool = True  # swallow a single printable hotkey key globally

    # STT
    model: str = "base.en"
    model_dir: str = "./models/faster-whisper-base.en"
    # Offline invariant: when the model is not found locally, refuse to run
    # rather than silently downloading. Set true to permit a HuggingFace fetch
    # (which is then logged loudly, never silent).
    allow_download: bool = False
    compute_type: str = "int8"
    cpu_threads: int = 0
    language: str = "en"
    beam_size: int = 1
    vad_filter: bool = True
    min_silence_duration_ms: int = 500

    # Audio
    device_index: int | None = None
    sample_rate: int = 16000
    # Safety cap on a single recording. Toggle mode has no auto-stop, so an
    # abandoned recording would otherwise grow RAM without bound. 0 = no cap.
    max_capture_seconds: int = 300

    # Output
    output_mode: str = "paste"  # "paste" | "type" | "clipboard-only"
    restore_clipboard: bool = False
    restore_delay_ms: int = 600
    paste_settle_ms: int = 30

    # Startup
    warm_start: bool = True

    # ---- model resolution -------------------------------------------------
    def model_search_roots(self) -> list[Path]:
        """Directories searched for a faster-whisper-<name> model, in order.

        1. %LOCALAPPDATA%/whisper-ptt/models  — canonical; works when installed.
        2. <repo>/models                      — source-run / dev fallback.
        3. parent of a configured model_dir   — back-compat with older configs.
        """
        roots: list[Path] = [models_dir(), PROJECT_ROOT / "models"]
        if self.model_dir:
            p = Path(self.model_dir)
            if not p.is_absolute():
                p = (PROJECT_ROOT / p).resolve()
            roots.append(p.parent)
        out: list[Path] = []
        for r in roots:  # de-dupe, preserve order
            if r not in out:
                out.append(r)
        return out

    def find_local_model(self, name: str) -> Path | None:
        """First existing faster-whisper-<name> dir across the search roots."""
        for root in self.model_search_roots():
            cand = root / f"faster-whisper-{name}"
            if cand.exists():
                return cand
        return None

    def resolve_model(self) -> tuple[str, bool]:
        """Return (source_for_WhisperModel, is_local).

        Never silently reaches the network: raises ModelNotFound when the model
        is unavailable locally and allow_download is false.
        """
        # Escape hatch: `model` may be an absolute path to a CT2 model dir.
        p = Path(self.model)
        if p.is_absolute() and p.exists():
            return str(p), True
        local = self.find_local_model(self.model)
        if local is not None:
            return str(local), True
        if self.allow_download:
            return self.model, False  # WhisperModel fetches by name (logged loud)
        raise ModelNotFound(self.model, self.model_search_roots())

    def model_source(self) -> str:
        """Back-compat shim: the local path or name for WhisperModel."""
        return self.resolve_model()[0]

    def validate(self) -> None:
        if self.mode not in ("ptt", "toggle"):
            raise ValueError(f"mode must be ptt|toggle, got {self.mode!r}")
        if self.output_mode not in ("paste", "type", "clipboard-only"):
            raise ValueError(f"output_mode invalid: {self.output_mode!r}")
        if self.compute_type not in ("int8", "int8_float32", "float32"):
            raise ValueError(f"compute_type invalid: {self.compute_type!r}")


def _coerce_device_index(raw) -> int | None:
    if raw in (None, "", "null", "none", "None"):
        return None
    return int(raw)


def load_config(seed_if_missing: bool = True) -> Config:
    """Load %APPDATA%\\whisper-ptt\\config.toml, seeding from the example once."""
    path = config_path()
    if not path.exists() and seed_if_missing and EXAMPLE_CONFIG.exists():
        config_dir().mkdir(parents=True, exist_ok=True)
        shutil.copyfile(EXAMPLE_CONFIG, path)

    data: dict = {}
    if path.exists():
        with open(path, "rb") as fh:
            data = tomllib.load(fh)

    known = {f.name for f in fields(Config)}
    kwargs = {}
    for key, val in data.items():
        if key not in known:
            continue
        if key == "device_index":
            kwargs[key] = _coerce_device_index(val)
        else:
            kwargs[key] = val

    cfg = Config(**kwargs)
    cfg.validate()
    return cfg
