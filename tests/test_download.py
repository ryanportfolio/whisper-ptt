"""whisper_ptt.download: repo map + destination dir + unknown-model error.

Framework-free; monkeypatches huggingface_hub.snapshot_download so no network
runs. Mirrors test_device_resolution.py.

    uv run python tests/test_download.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> int:
    import huggingface_hub

    from whisper_ptt import download

    calls: dict = {}

    def fake_snapshot(**kw):
        calls.clear()
        calls.update(kw)
        d = Path(kw["local_dir"])
        d.mkdir(parents=True, exist_ok=True)
        (d / "model.bin").write_bytes(b"x")  # emulate hf writing into local_dir
        return kw["local_dir"]

    # download_model does `from huggingface_hub import snapshot_download` at call
    # time, so patching the module attribute is enough.
    huggingface_hub.snapshot_download = fake_snapshot

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        dest = download.download_model("small.en", dest_root=root)
        assert dest == root / "faster-whisper-small.en", dest
        assert dest.exists(), dest
        assert calls["repo_id"] == "Systran/faster-whisper-small.en", calls
        assert "*.bin" in calls["allow_patterns"], calls
        print("ok: download_model targets the right repo + dest dir")

        try:
            download.download_model("does-not-exist", dest_root=root)
        except ValueError as exc:
            assert "unknown model" in str(exc), exc
            print("ok: unknown model raises ValueError")
        else:
            print("FAIL: unknown model did not raise")
            return 1

    assert download.model_repo("base.en") == "Systran/faster-whisper-base.en"
    assert download.model_repo("nope") is None
    assert "small.en" in download.MODEL_SIZE and "base.en" in download.KNOWN_MODELS
    print("ok: repo map + size/known metadata are consistent")

    print("ALL_DOWNLOAD_TESTS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
