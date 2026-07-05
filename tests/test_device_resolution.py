"""Input-device resolution: a pinned/default index that can't actually capture
must not be opened.

Regression guard for a real field failure: the app opened an *output* device
("Realtek Digital Output", 0 input channels) as a mic. PortAudio opens the
InputStream without error but delivers zero frames, so every dictation produced
"no audio captured" with no words. `_resolve_device` now rejects any index whose
`max_input_channels` is 0 (or that doesn't exist) and falls back to a working
input.

Runnable with no test framework and no real audio hardware:
    uv run python tests/test_device_resolution.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import whisper_ptt.audio as audio_mod  # noqa: E402
from whisper_ptt.config import Config  # noqa: E402

# Contiguous table so list index == device index, matching PortAudio.
_TABLE = {
    0: {"name": "Sound Mapper", "max_input_channels": 2, "max_output_channels": 0, "hostapi": 0, "default_samplerate": 44100},
    1: {"name": "EPOS Mic",     "max_input_channels": 1, "max_output_channels": 0, "hostapi": 0, "default_samplerate": 44100},
    2: {"name": "Speakers",     "max_input_channels": 0, "max_output_channels": 2, "hostapi": 1, "default_samplerate": 48000},
    3: {"name": "Digital Out",  "max_input_channels": 0, "max_output_channels": 2, "hostapi": 1, "default_samplerate": 192000},
}
_HOSTAPIS = [
    {"name": "MME", "default_input_device": 1},
    {"name": "Windows WASAPI", "default_input_device": -1},
]


class _Default:
    def __init__(self, device):
        self.device = device


class _FakeSD:
    def __init__(self, default_device):
        self.default = _Default(default_device)

    def query_devices(self, index=None):
        if index is None:
            return [_TABLE[k] for k in sorted(_TABLE)]
        if index not in _TABLE:
            raise ValueError(f"no device {index}")  # PortAudio raises for bad index
        return _TABLE[index]

    def query_hostapis(self):
        return _HOSTAPIS


def _resolve(device_index, default_device=(1, 2)):
    audio_mod.sd = _FakeSD(list(default_device))
    cap = audio_mod.AudioCapture(Config(device_index=device_index))
    return cap._resolve_device()


def test_pinned_output_device_falls_back():
    # index 3 is output-only -> must not be honored; fall back to default input.
    assert _resolve(3) == 1, "output device should not be selected as a mic"
    print("ok: a pinned output device falls back to the default input")


def test_pinned_out_of_range_falls_back():
    assert _resolve(99) == 1, "stale/unknown index should fall back"
    print("ok: a pinned out-of-range index falls back to the default input")


def test_pinned_valid_input_is_honored():
    assert _resolve(1) == 1
    print("ok: a pinned valid input device is honored")


def test_default_input_used_when_unpinned():
    assert _resolve(None, default_device=(1, 2)) == 1
    print("ok: unpinned config uses the system default input")


def test_scan_when_default_is_unusable():
    # default input = -1 (none) -> scan by API preference finds the MME input.
    assert _resolve(None, default_device=(-1, 2)) == 1
    print("ok: falls back to an API-preference scan when no default input")


def main() -> int:
    test_pinned_output_device_falls_back()
    test_pinned_out_of_range_falls_back()
    test_pinned_valid_input_is_honored()
    test_default_input_used_when_unpinned()
    test_scan_when_default_is_unusable()
    print("ALL_DEVICE_RESOLUTION_TESTS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
