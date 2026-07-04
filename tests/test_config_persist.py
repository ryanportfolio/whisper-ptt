"""Config persistence tests: tray write-through and first-run seeding.

Runnable with no test framework and no network:
    uv run python tests/test_config_persist.py

Covers: save_settings replaces an existing key in place while preserving
comments, appends keys that are absent, round-trips through load_config, and
first-run seeding creates a config that parses with log_transcripts off.
"""
from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from whisper_ptt.config import config_path, load_config, save_settings  # noqa: E402


@contextmanager
def _appdata(tmp: Path):
    """Point the per-user config dir at a throwaway location for the test."""
    saved = os.environ.get("APPDATA")
    os.environ["APPDATA"] = str(tmp)
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = saved


def test_save_replaces_in_place_and_keeps_comments():
    with tempfile.TemporaryDirectory() as td:
        with _appdata(Path(td)):
            path = config_path()
            path.parent.mkdir(parents=True)
            path.write_text(
                "# my precious comment\n"
                'mode = "toggle"\n'
                "log_transcripts = false\n",
                encoding="utf-8",
            )
            save_settings({"mode": "ptt", "log_transcripts": True})
            text = path.read_text(encoding="utf-8")
            assert "# my precious comment" in text, text
            assert 'mode = "ptt"' in text and 'mode = "toggle"' not in text, text
            assert "log_transcripts = true" in text, text
    print("ok: save_settings replaces in place, comments preserved")


def test_save_appends_missing_key():
    with tempfile.TemporaryDirectory() as td:
        with _appdata(Path(td)):
            path = config_path()
            path.parent.mkdir(parents=True)
            path.write_text('mode = "toggle"\n', encoding="utf-8")
            save_settings({"log_transcripts": True})
            cfg = load_config()
            assert cfg.log_transcripts is True and cfg.mode == "toggle", cfg
    print("ok: save_settings appends a key that was absent")


def test_roundtrip_through_load():
    with tempfile.TemporaryDirectory() as td:
        with _appdata(Path(td)):
            load_config()  # seeds from the example
            save_settings({"model": "small.en", "log_transcripts": True})
            cfg = load_config()
            assert cfg.model == "small.en" and cfg.log_transcripts is True, cfg
    print("ok: saved settings round-trip through load_config")


def test_seed_defaults_are_private():
    with tempfile.TemporaryDirectory() as td:
        with _appdata(Path(td)):
            cfg = load_config()
            assert config_path().exists(), "first run should seed config.toml"
            assert cfg.log_transcripts is False, "transcript logging must default off"
    print("ok: first-run seed parses, log_transcripts defaults off")


def main() -> int:
    test_save_replaces_in_place_and_keeps_comments()
    test_save_appends_missing_key()
    test_roundtrip_through_load()
    test_seed_defaults_are_private()
    print("ALL_PERSIST_TESTS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
