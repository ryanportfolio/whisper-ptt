"""Model-resolution tests: enforce the offline-first invariant.

Runnable with no test framework and no network:
    uv run python tests/test_model_resolution.py

Covers: absolute-path escape hatch, discovery in the data dir vs. repo fallback
(and their priority), and the two missing-model outcomes — refuse (default) vs.
download-permitted.
"""
from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from whisper_ptt.config import Config, ModelNotFound, models_dir  # noqa: E402


@contextmanager
def _localappdata(tmp: Path):
    """Point the per-user data dir at a throwaway location for the test."""
    saved = os.environ.get("LOCALAPPDATA")
    os.environ["LOCALAPPDATA"] = str(tmp)
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = saved


def test_absolute_path_escape_hatch():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "faster-whisper-custom"
        d.mkdir()
        src, is_local = Config(model=str(d), model_dir="").resolve_model()
        assert src == str(d) and is_local, (src, is_local)
    print("ok: absolute-path escape hatch")


def test_found_in_data_dir_and_priority():
    with tempfile.TemporaryDirectory() as td:
        with _localappdata(Path(td)):
            md = models_dir()
            (md / "faster-whisper-base.en").mkdir(parents=True)
            # model_dir="" so only data-dir + repo roots are searched. base.en
            # also exists in <repo>/models, so this asserts data-dir wins.
            src, is_local = Config(model="base.en", model_dir="").resolve_model()
            assert is_local and Path(src) == md / "faster-whisper-base.en", src
    print("ok: found in data dir (priority over repo fallback)")


def test_missing_refuses_by_default():
    with tempfile.TemporaryDirectory() as td:
        with _localappdata(Path(td)):
            cfg = Config(model="nonesuch.en", model_dir="", allow_download=False)
            try:
                cfg.resolve_model()
            except ModelNotFound as exc:
                assert "nonesuch.en" in str(exc) and "fetch_model.py" in str(exc)
            else:
                raise AssertionError("expected ModelNotFound, got a result")
    print("ok: missing model refuses (offline invariant)")


def test_missing_allows_download_when_opted_in():
    with tempfile.TemporaryDirectory() as td:
        with _localappdata(Path(td)):
            src, is_local = Config(
                model="nonesuch.en", model_dir="", allow_download=True
            ).resolve_model()
            assert src == "nonesuch.en" and not is_local, (src, is_local)
    print("ok: missing model returns name when allow_download=true")


def main() -> int:
    test_absolute_path_escape_hatch()
    test_found_in_data_dir_and_priority()
    test_missing_refuses_by_default()
    test_missing_allows_download_when_opted_in()
    print("ALL_RESOLUTION_TESTS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
