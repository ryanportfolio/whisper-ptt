"""Settings + status window (tkinter/ttk).

Runs on the main thread and owns the Tk root; the tray runs detached. It talks
to the engine only through callables (the same decoupling the ``Tray`` uses), so
it can be constructed and exercised in isolation. Every engine->UI refresh is a
periodic ``root.after`` poll of plain getter callbacks — the worker thread never
touches tkinter, which is not thread-safe.
"""
from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import ttk

from .audio import list_input_devices
from .download import MODEL_SIZE
from .tray import _HOTKEY_CHOICES

log = logging.getLogger("whisper_ptt.window")

# state key -> (label, colour)
_STATE_TEXT = {
    "loading": ("Loading model…", "#b8860b"),
    "idle": ("Ready", "#2e7d32"),
    "recording": ("Recording…", "#c62828"),
    "transcribing": ("Transcribing…", "#1565c0"),
    "error": ("Error", "#c62828"),
}

_DEFAULT_DEVICE = "System default"
_MODELS = [("base.en", "base.en (fast)"), ("small.en", "small.en (accurate)")]

_POLL_MS = 150
_MIC_TEST_TICK_MS = 100
_MIC_TEST_TICKS = 30            # ~3 seconds
_MIC_SIGNAL_RMS = 0.005        # peak RMS above this = a real signal
_DL_POLL_MS = 200              # poll the download thread's result from the UI


class SettingsWindow:
    def __init__(self, root, *,
                 get_state, get_last_result,
                 get_mode, set_mode,
                 get_model, set_model, model_installed,
                 get_hotkey, set_hotkey,
                 get_device, set_device,
                 mic_level, set_mic_test,
                 on_open_config, on_quit,
                 download_model=None,
                 should_quit=lambda: False,
                 list_devices=list_input_devices):
        self.root = root
        self._get_state = get_state
        self._get_last_result = get_last_result
        self._get_mode = get_mode
        self._set_mode = set_mode
        self._get_model = get_model
        self._set_model = set_model
        self._model_installed = model_installed
        self._get_hotkey = get_hotkey
        self._set_hotkey = set_hotkey
        self._get_device = get_device
        self._set_device = set_device
        self._mic_level = mic_level
        self._set_mic_test = set_mic_test
        self._on_open_config = on_open_config
        self._on_quit = on_quit
        self._download_model = download_model
        self._should_quit = should_quit
        self._list_devices = list_devices

        self._devices: list[tuple[int, str]] = []
        self._testing = False
        self._test_peak = 0.0
        self._test_ticks = 0
        self._downloading = False
        self._dl_name = ""
        self._dl_result: tuple[str, str] | None = None

        root.title("whisper-ptt")
        root.resizable(False, False)
        try:
            root.protocol("WM_DELETE_WINDOW", self.hide)
        except Exception:  # noqa: BLE001 — a bare Tk in a test may lack a WM
            pass

        self._build()
        self._sync()
        self._poll_id = root.after(_POLL_MS, self._poll)

    # ---- construction -----------------------------------------------------
    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.grid(sticky="nsew")

        # Status ------------------------------------------------------------
        status = ttk.LabelFrame(outer, text="Status", padding=8)
        status.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._state_lbl = ttk.Label(status, text="…", font=("Segoe UI", 11, "bold"))
        self._state_lbl.grid(row=0, column=0, sticky="w")
        self._detail_lbl = ttk.Label(status, text="")
        self._detail_lbl.grid(row=1, column=0, sticky="w", pady=(2, 0))
        self._last_lbl = ttk.Label(status, text="", foreground="#555")
        self._last_lbl.grid(row=2, column=0, sticky="w", pady=(2, 0))

        # Microphone --------------------------------------------------------
        mic = ttk.LabelFrame(outer, text="Microphone", padding=8)
        mic.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        mic.columnconfigure(0, weight=1)
        self._device_var = tk.StringVar()
        self._device_cb = ttk.Combobox(mic, textvariable=self._device_var,
                                        state="readonly", width=34)
        self._device_cb.grid(row=0, column=0, sticky="ew")
        self._device_cb.bind("<<ComboboxSelected>>", self._on_device_pick)
        self._test_btn = ttk.Button(mic, text="Test", width=8, command=self._on_test)
        self._test_btn.grid(row=0, column=1, padx=(6, 0))
        self._level = ttk.Progressbar(mic, maximum=100, length=200)
        self._level.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._mic_msg = ttk.Label(mic, text="Pick your mic, then Test.", foreground="#555")
        self._mic_msg.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # Model -------------------------------------------------------------
        model = ttk.LabelFrame(outer, text="Speech model", padding=8)
        model.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        model.columnconfigure(0, weight=1)
        self._model_var = tk.StringVar()
        self._model_cb = ttk.Combobox(model, textvariable=self._model_var,
                                      state="readonly", width=34)
        self._model_cb.grid(row=0, column=0, sticky="ew")
        self._model_cb.bind("<<ComboboxSelected>>", self._on_model_pick)
        self._download_btn = ttk.Button(model, text="Download", width=10,
                                        command=self._on_download, state="disabled")
        self._download_btn.grid(row=0, column=1, padx=(6, 0))
        self._dl_bar = ttk.Progressbar(model, mode="indeterminate", length=200)
        self._dl_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._dl_bar.grid_remove()  # shown only while a download runs
        self._model_msg = ttk.Label(model, text="", foreground="#555")
        self._model_msg.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # Mode + hotkey -----------------------------------------------------
        row = ttk.Frame(outer)
        row.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        mode = ttk.LabelFrame(row, text="Mode", padding=8)
        mode.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._mode_var = tk.StringVar()
        ttk.Radiobutton(mode, text="Push-to-talk", value="ptt",
                        variable=self._mode_var, command=self._on_mode_pick).grid(sticky="w")
        ttk.Radiobutton(mode, text="Toggle", value="toggle",
                        variable=self._mode_var, command=self._on_mode_pick).grid(sticky="w")
        hk = ttk.LabelFrame(row, text="Hotkey", padding=8)
        hk.grid(row=0, column=1, sticky="nsew")
        self._hotkey_var = tk.StringVar()
        self._hotkey_cb = ttk.Combobox(hk, textvariable=self._hotkey_var,
                                       state="readonly", width=18)
        self._hotkey_cb.grid(sticky="ew")
        self._hotkey_cb.bind("<<ComboboxSelected>>", self._on_hotkey_pick)

        # Footer ------------------------------------------------------------
        footer = ttk.Frame(outer)
        footer.grid(row=4, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, text="Open config file",
                   command=self._on_open_config).grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="Quit", command=self._quit).grid(row=0, column=1, sticky="e")

    # ---- one-time value population ---------------------------------------
    def _sync(self) -> None:
        """Populate combobox choices + current selections from the getters."""
        self._devices = list(self._list_devices())
        self._device_cb["values"] = [_DEFAULT_DEVICE] + [
            f"{idx}: {name}" for idx, name in self._devices]
        self._device_var.set(self._device_label(self._get_device()))

        self._model_cb["values"] = [self._model_label(name) for name, _ in _MODELS]
        self._model_var.set(self._model_label(self._get_model()))
        if not self._downloading:
            self._update_download_btn()

        self._hotkey_cb["values"] = self._hotkey_values()
        self._hotkey_var.set(self._hotkey_label(self._get_hotkey()))

        self._mode_var.set(self._get_mode())

    # ---- label <-> value helpers -----------------------------------------
    def _device_label(self, index) -> str:
        if index is None:
            return _DEFAULT_DEVICE
        for idx, name in self._devices:
            if idx == index:
                return f"{idx}: {name}"
        return f"{index}: (unavailable)"

    def _device_from_label(self, label: str):
        if label == _DEFAULT_DEVICE or ":" not in label:
            return None
        try:
            return int(label.split(":", 1)[0])
        except ValueError:
            return None

    def _model_label(self, name: str) -> str:
        pretty = dict(_MODELS).get(name, name)
        return pretty if self._model_installed(name) else f"{pretty} — not installed"

    def _model_from_label(self, label: str) -> str:
        for name, _ in _MODELS:
            if self._model_label(name) == label:
                return name
        return self._get_model()

    def _hotkey_values(self) -> list[str]:
        vals = [self._hotkey_label(v) for v, _ in _HOTKEY_CHOICES]
        cur = self._get_hotkey()
        if cur not in {v for v, _ in _HOTKEY_CHOICES}:
            vals.insert(0, f"{cur} (from config)")
        return vals

    def _hotkey_label(self, chord: str) -> str:
        for v, label in _HOTKEY_CHOICES:
            if v == chord:
                return label
        return f"{chord} (from config)"

    def _hotkey_from_label(self, label: str) -> str:
        for v, lbl in _HOTKEY_CHOICES:
            if lbl == label:
                return v
        return label.replace(" (from config)", "")

    # ---- widget callbacks -------------------------------------------------
    def _on_device_pick(self, _event=None) -> None:
        self._set_device(self._device_from_label(self._device_var.get()))
        self._mic_msg.config(text="Device changed. Test to confirm it captures.")

    def _on_model_pick(self, _event=None) -> None:
        name = self._model_from_label(self._model_var.get())
        if not self._model_installed(name):
            # Don't switch the engine to a missing model (the offline guard would
            # refuse it), but leave the box on this pick so the user can Download
            # it. Only Download reaches the network, and only on an explicit click.
            self._update_download_btn()
            if self._download_model is not None:
                self._model_msg.config(
                    text=f"{name} not installed — click Download "
                         f"({MODEL_SIZE.get(name, '')}).", foreground="#b8860b")
            else:
                self._model_msg.config(text=f"{name} is not installed.",
                                       foreground="#b8860b")
            return
        self._download_btn.config(state="disabled")
        self._model_msg.config(text="")
        self._set_model(name)

    def _update_download_btn(self) -> None:
        """Enable Download only for a selected model that isn't installed yet."""
        name = self._model_from_label(self._model_var.get())
        can = (self._download_model is not None
               and not self._downloading
               and not self._model_installed(name))
        self._download_btn.config(state="normal" if can else "disabled")

    def _on_mode_pick(self) -> None:
        self._set_mode(self._mode_var.get())

    def _on_hotkey_pick(self, _event=None) -> None:
        self._set_hotkey(self._hotkey_from_label(self._hotkey_var.get()))

    def _quit(self) -> None:
        # Route through the engine; the poll loop below tears the root down once
        # `should_quit` flips, so window-Quit and tray-Quit share one teardown.
        self._on_quit()

    # ---- mic test ---------------------------------------------------------
    def _on_test(self) -> None:
        if self._testing:
            return
        self._testing = True
        self._test_peak = 0.0
        self._test_ticks = 0
        self._test_btn.config(state="disabled")
        self._mic_msg.config(text="Listening… say something.", foreground="#555")
        self._set_mic_test(True)
        self.root.after(_MIC_TEST_TICK_MS, self._mic_tick)

    def _mic_tick(self) -> None:
        level = 0.0
        try:
            level = float(self._mic_level())
        except Exception:  # noqa: BLE001
            level = 0.0
        self._test_peak = max(self._test_peak, level)
        self._level["value"] = min(100.0, level * 400.0)
        self._test_ticks += 1
        if self._test_ticks < _MIC_TEST_TICKS:
            self.root.after(_MIC_TEST_TICK_MS, self._mic_tick)
        else:
            self._end_test()

    def _end_test(self) -> None:
        self._set_mic_test(False)
        self._testing = False
        self._level["value"] = 0
        self._test_btn.config(state="normal")
        if self._test_peak >= _MIC_SIGNAL_RMS:
            self._mic_msg.config(text="✓ Mic OK — signal detected.", foreground="#2e7d32")
        else:
            self._mic_msg.config(
                text="✗ No/low signal. Pick a different mic (not an earphone/output) "
                     "or check it is unmuted.", foreground="#c62828")

    # ---- model download ---------------------------------------------------
    def _on_download(self) -> None:
        if self._downloading or self._download_model is None:
            return
        name = self._model_from_label(self._model_var.get())
        if self._model_installed(name):
            return
        self._downloading = True
        self._dl_name = name
        self._dl_result = None
        self._download_btn.config(state="disabled")
        self._model_cb.config(state="disabled")
        self._model_msg.config(
            text=f"Downloading {name} {MODEL_SIZE.get(name, '')} — one time, "
                 f"please wait…", foreground="#1565c0")
        self._dl_bar.grid()
        self._dl_bar.start(12)
        threading.Thread(target=self._download_worker, args=(name,),
                         daemon=True, name="model-download").start()
        self.root.after(_DL_POLL_MS, self._download_tick)

    def _download_worker(self, name: str) -> None:
        # Runs off the UI thread; touches only plain attributes the poll reads
        # (tkinter is not thread-safe, so no widget calls happen here).
        try:
            path = self._download_model(name)
            self._dl_result = ("ok", str(path))
        except Exception as exc:  # noqa: BLE001 — surfaced in the UI, never crashes
            log.exception("model download failed: %s", name)
            self._dl_result = ("err", f"{type(exc).__name__}: {exc}")

    def _download_tick(self) -> None:
        if self._dl_result is None:
            self.root.after(_DL_POLL_MS, self._download_tick)
            return
        kind, payload = self._dl_result
        self._downloading = False
        try:
            self._dl_bar.stop()
            self._dl_bar.grid_remove()
        except Exception:  # noqa: BLE001
            pass
        self._model_cb.config(state="readonly")
        if kind == "ok":
            # The model now resolves locally: re-tag the choices and switch to it.
            self._model_cb["values"] = [self._model_label(n) for n, _ in _MODELS]
            self._model_var.set(self._model_label(self._dl_name))
            self._model_msg.config(
                text=f"✓ Downloaded {self._dl_name} — switching to it.",
                foreground="#2e7d32")
            self._download_btn.config(state="disabled")
            self._set_model(self._dl_name)
        else:
            self._model_msg.config(text=f"✗ Download failed: {payload}",
                                   foreground="#c62828")
            self._update_download_btn()

    # ---- live refresh -----------------------------------------------------
    def _poll(self) -> None:
        if self._should_quit():
            try:
                self.root.destroy()  # ends mainloop; cancels pending after() jobs
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            self._refresh()
        finally:
            self._poll_id = self.root.after(_POLL_MS, self._poll)

    def _refresh(self) -> None:
        label, colour = _STATE_TEXT.get(self._get_state(), (self._get_state(), "#000"))
        self._state_lbl.config(text=label, foreground=colour)
        self._detail_lbl.config(
            text=f"model {self._get_model()}   •   hotkey {self._get_hotkey()}"
                 f"   •   {self._get_mode()}")
        last = self._get_last_result()
        self._last_lbl.config(text=f"Last: {last}" if last else "")
        # Reflect external changes (e.g. the tray menu) without stealing focus.
        if self._mode_var.get() != self._get_mode():
            self._mode_var.set(self._get_mode())

    # ---- show / hide ------------------------------------------------------
    def show(self) -> None:
        try:
            self._sync()
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception:  # noqa: BLE001
            log.debug("show() before root ready")

    def hide(self) -> None:
        try:
            self.root.withdraw()
        except Exception:  # noqa: BLE001
            pass

    def run(self) -> None:
        """Blocks on the tk main loop (call on the main thread)."""
        self.root.mainloop()
