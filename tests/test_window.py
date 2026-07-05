"""Settings window construction + wiring.

Builds the tkinter SettingsWindow against stub callbacks and exercises the
device / model / mode / hotkey pickers plus the mic-test verdict logic — no
engine, no audio, no model. Requires a Tk display; where Tk can't initialize
(headless CI), it prints SKIP and exits 0, mirroring how the audio paths are
hardware-gated.

    uv run python tests/test_window.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import tkinter as tk  # noqa: E402


def _make(root):
    from whisper_ptt.window import SettingsWindow  # noqa: PLC0415

    calls = {"mode": None, "model": None, "hotkey": None, "device": "unset",
             "mic_test": [], "quit": 0}
    installed = {"base.en": True, "small.en": False}
    state = {"state": "idle", "last": "", "mode": "toggle", "model": "base.en",
             "hotkey": "`", "device": None, "level": 0.0}

    def fake_download(name):
        installed[name] = True  # emulate a completed fetch making it resolvable
        return f"C:/models/faster-whisper-{name}"

    win = SettingsWindow(
        root,
        get_state=lambda: state["state"],
        get_last_result=lambda: state["last"],
        get_mode=lambda: state["mode"],
        set_mode=lambda v: calls.__setitem__("mode", v),
        get_model=lambda: state["model"],
        set_model=lambda v: calls.__setitem__("model", v),
        model_installed=lambda n: installed[n],
        get_hotkey=lambda: state["hotkey"],
        set_hotkey=lambda v: calls.__setitem__("hotkey", v),
        get_device=lambda: state["device"],
        set_device=lambda v: calls.__setitem__("device", v),
        mic_level=lambda: state["level"],
        set_mic_test=lambda on: calls["mic_test"].append(on),
        on_open_config=lambda: None,
        on_quit=lambda: calls.__setitem__("quit", calls["quit"] + 1),
        download_model=fake_download,
        should_quit=lambda: False,
        list_devices=lambda: [(1, "EPOS Mic"),
                              (15, "Headset Microphone (EPOS IMPACT 60)")],
    )
    return win, calls, installed


def main() -> int:
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"SKIP: no Tk display ({exc})")
        return 0
    root.withdraw()  # never flash a real window during the test
    try:
        win, calls, installed = _make(root)
        root.update()  # realize widgets; 150ms poll hasn't elapsed, so it's inert

        vals = list(win._model_cb["values"])
        assert any("not installed" in v for v in vals), vals
        print("ok: an uninstalled model is tagged in the dropdown")

        win._device_var.set("15: Headset Microphone (EPOS IMPACT 60)")
        win._on_device_pick()
        assert calls["device"] == 15, calls
        win._device_var.set("System default")
        win._on_device_pick()
        assert calls["device"] is None, calls
        print("ok: device picker maps label -> index / None")

        # An uninstalled model must not switch the engine (offline guard), but
        # the box stays on the pick and Download turns on.
        win._model_var.set(win._model_label("small.en"))
        win._on_model_pick()
        assert calls["model"] is None, calls
        assert "small.en" in win._model_var.get(), win._model_var.get()
        assert str(win._download_btn.cget("state")) == "normal", win._download_btn.cget("state")
        print("ok: uninstalled model enables Download, does not switch engine")

        # Drive a completed download directly (worker + tick, no real thread):
        # it flips installed, re-tags, and auto-switches to the new model.
        win._downloading = True
        win._dl_name = "small.en"
        win._download_worker("small.en")   # fake_download makes it "installed"
        win._download_tick()
        assert installed["small.en"] is True
        assert calls["model"] == "small.en", calls
        assert not win._downloading
        print("ok: completed download installs + auto-selects the model")

        win._model_var.set(win._model_label("base.en"))
        win._on_model_pick()
        assert calls["model"] == "base.en", calls
        print("ok: installed model selection switches")

        win._mode_var.set("ptt")
        win._on_mode_pick()
        assert calls["mode"] == "ptt", calls
        win._hotkey_var.set("F9")
        win._on_hotkey_pick()
        assert calls["hotkey"] == "f9", calls
        print("ok: mode + hotkey pickers reach the setters")

        win._on_test()
        assert calls["mic_test"][-1] is True, calls
        win._test_peak = 0.1  # simulate a strong signal
        win._end_test()
        assert calls["mic_test"][-1] is False, calls
        assert "OK" in win._mic_msg.cget("text"), win._mic_msg.cget("text")
        win._on_test()
        win._test_peak = 0.0   # silence
        win._end_test()
        assert "No/low" in win._mic_msg.cget("text"), win._mic_msg.cget("text")
        print("ok: mic test reports OK on signal and warns on silence")

        print("ALL_WINDOW_TESTS_OK")
        return 0
    finally:
        try:
            root.destroy()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    raise SystemExit(main())
