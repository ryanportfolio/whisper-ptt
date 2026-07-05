"""Entry point: wires hotkey -> capture -> transcribe -> output, behind a tray.

Threading model:
  - main thread .......... pystray message loop (Tray.run)
  - worker thread ........ serializes start/stop/transcribe/emit/reload
  - pynput listener thread global hotkey hook (callbacks only enqueue)
  - PortAudio thread ..... audio callback fills the capture buffer
  - boot thread .......... model load + stream open at startup
"""

from __future__ import annotations

import argparse
import logging
import queue
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import replace
from logging.handlers import RotatingFileHandler

from . import __version__
from .audio import AudioCapture, list_input_devices
from .config import (Config, ModelNotFound, config_dir, config_path,
                     load_config, save_settings)
from .download import download_model
from .hotkey import HotkeyController
from .output import OutputEmitter
from .transcriber import Transcriber
from .tray import Tray
from .window import SettingsWindow

log = logging.getLogger("whisper_ptt")


class Engine:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.audio = AudioCapture(cfg)
        self.transcriber = Transcriber(cfg)
        self.output = OutputEmitter(cfg)
        self.tray: Tray | None = None
        self.window: SettingsWindow | None = None
        self.hotkey: HotkeyController | None = None

        self._q: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._ready = False
        self._recording = False
        self._transcribing = False  # true while the worker blocks on transcribe
        self._monitoring = False    # true during a window "Test microphone" run
        self._press_mode = cfg.mode  # mode latched at the start of a press
        self.config_error: str | None = None  # set if config failed to load
        # Polled by the window (tk thread) for a thread-safe UI refresh; the
        # worker never touches tkinter directly.
        self._state_str = "loading"
        self._last_result = ""
        self._quitting = False

    # ---- lifecycle --------------------------------------------------------
    def start_worker(self) -> None:
        self._worker = threading.Thread(target=self._run, daemon=True, name="engine")
        self._worker.start()

    def boot(self) -> None:
        self._set_state("loading")
        try:
            self.transcriber.load()
            self.audio.open()
            if self.cfg.warm_start:
                self.transcriber.warm_start()
            self._ready = True
            self._set_state("idle")
            log.info("ready (model=%s, mode=%s, hotkey=%s)",
                     self.cfg.model, self.cfg.mode, self.cfg.hotkey)
            if self.config_error is not None:
                self._notify("config error, running on defaults",
                             self.config_error)
        except ModelNotFound as exc:
            log.error("boot failed: %s", exc)
            self._last_result = f"model {self.cfg.model} not installed"
            self._notify(
                f"model {self.cfg.model} not installed",
                f"Run: python scripts/fetch_model.py {self.cfg.model}")
            self._set_state("error")
        except Exception:  # noqa: BLE001
            log.exception("boot failed")
            self._set_state("error")

    def shutdown(self) -> None:
        self._quitting = True  # the window poll (tk thread) tears down the root
        self._q.put(("shutdown", None))
        try:
            self.audio.close()
        except Exception:  # noqa: BLE001
            pass

    # ---- hotkey callbacks (trivial: enqueue only) -------------------------
    def on_press(self) -> None:
        if not self._ready:
            return
        # The single worker runs transcribe+emit inline, and the mic does not
        # capture while it does. Starting a new dictation now would record into
        # a dead buffer and silently lose the user's speech, so drop the trigger
        # and tell them instead. (A future decoupled-transcribe design could
        # allow barge-in.)
        if self._transcribing:
            log.info("busy transcribing; hotkey ignored, speak again after it finishes")
            return
        # Latch the mode for this whole press so the matching release uses the
        # same mode even if the tray flips it mid-press (else recording sticks).
        self._press_mode = self.cfg.mode
        if self._press_mode == "ptt":
            self._q.put(("start", None))
        else:  # toggle
            self._q.put(("toggle", None))

    def on_release(self) -> None:
        if not self._ready:
            return
        if self._press_mode == "ptt":
            self._q.put(("stop", None))

    # ---- tray callbacks ---------------------------------------------------
    def _persist(self, values: dict) -> None:
        """Write tray-changed settings through to config.toml, best-effort.

        A locked or read-only config must not crash the tray thread; the
        in-memory setting still applies for this run.
        """
        try:
            save_settings(values)
        except Exception:  # noqa: BLE001
            log.warning("could not persist %s to config", values, exc_info=True)

    def set_mode(self, mode: str) -> None:
        self.cfg.mode = mode
        log.info("mode -> %s", mode)
        self._persist({"mode": mode})
        # End any in-flight capture cleanly so a mode flip can't orphan it.
        if self._recording:
            self._q.put(("stop", None))

    def set_log_transcripts(self, enabled: bool) -> None:
        self.cfg.log_transcripts = enabled
        log.info("log transcripts -> %s", enabled)
        self._persist({"log_transcripts": enabled})

    def set_hotkey(self, chord: str) -> None:
        if chord == self.cfg.hotkey:
            return
        # Build (and so validate) the replacement hook before tearing down the
        # working one — a bad chord must leave the current hotkey in place.
        try:
            new = HotkeyController(
                chord, self.on_press, self.on_release,
                debounce_ms=self.cfg.debounce_ms, suppress=self.cfg.suppress_hotkey)
        except Exception:  # noqa: BLE001
            log.exception("invalid hotkey %r; keeping %r", chord, self.cfg.hotkey)
            self._notify("invalid hotkey",
                         f"{chord!r} could not be parsed; keeping {self.cfg.hotkey!r}")
            return
        # End any in-flight capture: in PTT mode the release event would land
        # on the stopped listener and never arrive, wedging the recording.
        if self._recording:
            self._q.put(("stop", None))
        if self.hotkey is not None:
            self.hotkey.stop()
        new.start()
        self.hotkey = new
        self.cfg.hotkey = chord
        log.info("hotkey -> %s", chord)
        self._persist({"hotkey": chord})

    def request_model_change(self, model: str) -> None:
        if model == self.cfg.model:
            return
        self._q.put(("reload", model))

    def set_device(self, index: int | None) -> None:
        """Change the input device: reopen the capture stream on the worker."""
        if index == self.cfg.device_index:
            return
        self._q.put(("set_device", index))

    def monitor_mic(self, on: bool) -> None:
        """Gate a transcribe-less capture so the window can show a live level."""
        self._q.put(("monitor_on" if on else "monitor_off", None))

    def open_config(self) -> None:
        path = config_path()
        # Open in Notepad rather than the shell "open" verb: .toml usually has
        # no committed default handler, so os.startfile pops Windows' "how do
        # you want to open this file?" chooser every launch. Notepad ships on
        # every Windows box and opens the config directly, with no picker.
        try:
            subprocess.Popen(["notepad.exe", str(path)])
        except OSError:
            log.warning("could not open config at %s", path)

    # ---- worker -----------------------------------------------------------
    def _set_state(self, state: str) -> None:
        self._state_str = state  # window polls this on the tk thread
        if self.tray is not None:
            self.tray.set_state(state)

    def _notify(self, title: str, message: str) -> None:
        """Best-effort tray balloon; never raise (backend/support varies)."""
        if self.tray is None:
            return
        try:
            self.tray.icon.notify(message, title)
        except Exception:  # noqa: BLE001
            log.debug("notify unsupported: %s / %s", title, message)

    def _run(self) -> None:
        while True:
            cmd, arg = self._q.get()
            try:
                if cmd == "shutdown":
                    return
                elif cmd == "start":
                    self._do_start()
                elif cmd == "stop":
                    self._do_stop()
                elif cmd == "toggle":
                    self._do_stop() if self._recording else self._do_start()
                elif cmd == "reload":
                    self._do_reload(arg)
                elif cmd == "set_device":
                    self._do_set_device(arg)
                elif cmd == "monitor_on":
                    if self._ready and not self._recording and not self._transcribing:
                        self._monitoring = True
                        self.audio.start()
                elif cmd == "monitor_off":
                    if self._monitoring:
                        self._monitoring = False
                        self.audio.stop()  # discard; the test never transcribes
            except Exception:  # noqa: BLE001 — keep the worker alive
                log.exception("worker error on %s", cmd)
                self._set_state("error")
                self._recording = False
                self._monitoring = False

    def _do_start(self) -> None:
        if self._recording:
            return
        self._monitoring = False  # a real dictation takes over from a mic test
        self._recording = True
        self.audio.start()
        self._set_state("recording")

    def _do_stop(self) -> None:
        if not self._recording:
            return
        self._recording = False
        audio = self.audio.stop()
        if audio.size == 0:
            log.warning("no audio captured. Is a microphone connected and enabled? "
                        "Try: python -m whisper_ptt --test-capture / --list-devices")
            # The windowed exe has no console, so a swallowed log leaves the user
            # staring at a dictation that produced nothing. Surface it on the tray
            # and in the window's status line.
            self._last_result = "no audio captured — check the mic"
            self._notify(
                "no audio captured",
                "No microphone input detected. Check the mic is connected, "
                "unmuted, and set as the default recording device in Windows.")
            self._set_state("idle")
            return
        self._set_state("transcribing")
        self._transcribing = True
        try:
            text = self.transcriber.transcribe(audio)
            # Privacy: dictated content reaches the persistent log only by
            # opt-in; the default records lengths, never words.
            if self.cfg.log_transcripts:
                log.info("transcript (%d samples): %r", audio.size, text)
            else:
                log.info("transcript: %d samples -> %d chars", audio.size, len(text))
            self.output.emit(text)
            # Same privacy split for the on-screen status line.
            if not text.strip():
                self._last_result = "no speech detected"
            elif self.cfg.log_transcripts:
                self._last_result = f'pasted: "{text.strip()[:50]}"'
            else:
                self._last_result = f"pasted {len(text)} chars"
        finally:
            self._transcribing = False
        self._set_state("idle")

    def _do_reload(self, model: str) -> None:
        if not self._ready:
            log.warning("ignoring model change to %s: engine not ready", model)
            return
        # Discard any in-flight capture before swapping the model.
        if self._recording:
            self._recording = False
            self.audio.stop()

        # Require the model to be bundled locally; never silently network-fetch
        # (the app is offline-first). small.en must be fetched ahead of time.
        cand = self.cfg.find_local_model(model)
        if cand is None:
            log.error("model %s not installed; run: python scripts/fetch_model.py %s",
                      model, model)
            self._last_result = f"{model} not installed — kept {self.cfg.model}"
            self._notify(f"model {model} not installed",
                         f"Run: python scripts/fetch_model.py {model}")
            # The engine is still healthy on the current model — return to idle
            # rather than sticking a scary error icon on a working app.
            self._set_state("idle")
            return

        self._set_state("loading")
        # Build + load on a local first; swap in only on success so a failure
        # leaves the working model in place instead of wedging the app.
        new_cfg = replace(self.cfg, model=model, model_dir=str(cand))
        new_tr = Transcriber(new_cfg)
        try:
            new_tr.load()
            if new_cfg.warm_start:
                new_tr.warm_start()
        except Exception:  # noqa: BLE001
            log.exception("model reload to %s failed; keeping %s", model, self.cfg.model)
            self._last_result = f"could not load {model} — kept {self.cfg.model}"
            self._set_state("idle")
            return

        self.transcriber = new_tr
        self.cfg.model = model
        self.cfg.model_dir = str(cand)
        self._persist({"model": model})
        self._last_result = f"model → {model}"
        self._set_state("idle")
        log.info("model reloaded -> %s", model)

    def _do_set_device(self, index: int | None) -> None:
        prev = self.cfg.device_index
        # Drop any in-flight capture/monitor, then reopen on the new device.
        if self._recording:
            self._recording = False
            try:
                self.audio.stop()
            except Exception:  # noqa: BLE001
                pass
        self._monitoring = False
        try:
            self.audio.close()
        except Exception:  # noqa: BLE001
            pass
        self.cfg.device_index = index
        try:
            self.audio.open()
        except Exception:  # noqa: BLE001
            log.exception("could not open device %s; reverting to %s", index, prev)
            self.cfg.device_index = prev
            try:
                self.audio.open()
            except Exception:  # noqa: BLE001
                log.exception("reverting to device %s also failed", prev)
                self._last_result = "device open failed"
                self._set_state("error")
                return
            self._last_result = f"device {index} unavailable — kept previous"
            self._set_state("idle")
            return
        # config stores an empty string for "system default", an int otherwise.
        self._persist({"device_index": "" if index is None else index})
        self._last_result = "input device updated"
        self._set_state("idle")
        log.info("input device -> %s", index)


def _setup_logging() -> None:
    handlers: list[logging.Handler] = []
    # Under pythonw.exe / a windowed frozen exe there is no console at all
    # (sys.stderr is None), so only attach a stream handler when one exists.
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    # Console-less runs would otherwise blackhole every log line. Add a
    # rotating file the user can inspect.
    try:
        d = config_dir()
        d.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(
            d / "whisper-ptt.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"))
    except Exception:  # noqa: BLE001 — logging must never block startup
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


def main() -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(prog="whisper-ptt")
    parser.add_argument("--list-devices", action="store_true",
                        help="list input audio devices and exit")
    parser.add_argument("--test-capture", action="store_true",
                        help="record ~1.5s from the resolved mic, report level, and exit")
    parser.add_argument("--selftest", action="store_true",
                        help="load the model, transcribe a dummy tone, and exit; "
                             "packaging smoke test, needs no audio device")
    parser.add_argument("--selftest-ui", action="store_true",
                        help="build the window + detached tray, pump the loop "
                             "briefly, and exit 0; GUI construction/threading smoke")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args()

    if args.version:
        print(f"whisper-ptt {__version__}")
        return 0

    if args.list_devices:
        for idx, name in list_input_devices():
            print(f"{idx:>3}  {name}")
        return 0

    if args.selftest:
        # End-to-end packaging check: config seeds, the model resolves
        # locally, CTranslate2/VAD binaries load, and a decode really runs.
        # Any failure raises -> nonzero exit, so CI can gate on it.
        # VAD off: it would strip the faint tone to nothing and the decoder
        # kernels would never execute (same reasoning as warm_start).
        import numpy as np
        cfg = replace(load_config(), vad_filter=False)
        tr = Transcriber(cfg)
        tr.load()
        n = cfg.sample_rate // 2
        t = np.arange(n, dtype=np.float32) / float(cfg.sample_rate)
        tone = (0.01 * np.sin(2.0 * np.pi * 220.0 * t)).astype(np.float32)
        text = tr.transcribe(tone)
        log.info("selftest ok: model=%s, %d samples -> %r", cfg.model, n, text)
        print(f"selftest ok: model {cfg.model} loaded, {n} samples -> {text!r}")
        return 0

    if args.test_capture:
        import time
        import numpy as np
        cfg = load_config()
        cap = AudioCapture(cfg)
        cap.open()
        print("recording ~1.5s - say something...")
        cap.start()
        time.sleep(1.5)
        buf = cap.stop()
        cap.close()
        rms = float(np.sqrt(np.mean(buf * buf))) if buf.size else 0.0
        peak = float(np.max(np.abs(buf))) if buf.size else 0.0
        print(f"captured {buf.size} samples ({buf.size / cfg.sample_rate:.2f}s) "
              f"rms={rms:.4f} peak={peak:.4f}")
        if buf.size == 0:
            print("NO AUDIO: no microphone is delivering data. Connect a mic, enable it, "
                  "and set it as the default recording device in Windows Sound settings.")
            return 2
        if rms < 1e-4:
            print("SILENT: a device opened but captured near-silence. Check the mic is "
                  "unmuted and is the default recording device.")
            return 3
        print("OK: microphone is capturing audio.")
        return 0

    # A hand-edited config (malformed TOML, bad device_index, invalid enum)
    # must not be a silent no-launch under pythonw. Fall back to defaults and
    # surface the reason after the tray comes up.
    config_error: str | None = None
    try:
        cfg = load_config()
    except Exception as exc:  # noqa: BLE001
        log.exception("config load failed; falling back to defaults")
        cfg = Config()
        config_error = f"{type(exc).__name__}: {exc}"
    log.info("config: %s", config_path())

    engine = Engine(cfg)
    engine.config_error = config_error

    # tkinter must own the main thread and its own mainloop; the tray therefore
    # runs detached (see docs/superpowers/specs/2026-07-05-settings-window-design).
    root = tk.Tk()
    window = SettingsWindow(
        root,
        get_state=lambda: engine._state_str,
        get_last_result=lambda: engine._last_result,
        get_mode=lambda: engine.cfg.mode,
        set_mode=engine.set_mode,
        get_model=lambda: engine.cfg.model,
        set_model=engine.request_model_change,
        model_installed=lambda name: engine.cfg.find_local_model(name) is not None,
        get_hotkey=lambda: engine.cfg.hotkey,
        set_hotkey=engine.set_hotkey,
        get_device=lambda: engine.cfg.device_index,
        set_device=engine.set_device,
        mic_level=lambda: engine.audio.rms,
        set_mic_test=engine.monitor_mic,
        on_open_config=engine.open_config,
        on_quit=engine.shutdown,
        download_model=download_model,
        should_quit=lambda: engine._quitting,
    )
    engine.window = window

    tray = Tray(
        get_mode=lambda: engine.cfg.mode,
        set_mode=engine.set_mode,
        get_model=lambda: engine.cfg.model,
        set_model=engine.request_model_change,
        get_log_transcripts=lambda: engine.cfg.log_transcripts,
        set_log_transcripts=engine.set_log_transcripts,
        get_hotkey=lambda: engine.cfg.hotkey,
        set_hotkey=engine.set_hotkey,
        on_open_config=engine.open_config,
        on_quit=engine.shutdown,
        on_show=window.show,
    )
    engine.tray = tray

    if args.selftest_ui:
        # Construction + threading smoke: no model load, audio, or hotkey.
        tray.icon.run_detached()
        root.after(500, root.destroy)
        root.mainloop()
        try:
            tray.icon.stop()
        except Exception:  # noqa: BLE001
            pass
        print("selftest-ui ok: window + detached tray built and torn down")
        return 0

    engine.hotkey = HotkeyController(
        cfg.hotkey, engine.on_press, engine.on_release,
        debounce_ms=cfg.debounce_ms, suppress=cfg.suppress_hotkey,
    )

    engine.start_worker()
    engine.hotkey.start()
    threading.Thread(target=engine.boot, daemon=True, name="boot").start()

    tray.icon.run_detached()  # background thread; frees the main thread for tk
    try:
        window.run()  # root.mainloop(); blocks on the main thread until quit
    finally:
        engine.shutdown()
        try:
            tray.icon.stop()
        except Exception:  # noqa: BLE001
            pass
        # engine.hotkey, not a local: a tray/window hotkey change swaps it.
        if engine.hotkey is not None:
            engine.hotkey.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
