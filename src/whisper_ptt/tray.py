"""System-tray UI (pystray): state icon + menu."""

from __future__ import annotations

import logging

import pystray
from pystray import Menu, MenuItem

from .icons import make_icon

log = logging.getLogger("whisper_ptt.tray")

# Curated hotkey choices for the tray picker; any pynput chord still works via
# the config file, and a custom config value shows up as an extra entry.
_HOTKEY_CHOICES = [
    ("`", "` (backtick)"),
    ("f8", "F8"),
    ("f9", "F9"),
    ("ctrl+alt+space", "Ctrl+Alt+Space"),
    ("ctrl+shift+d", "Ctrl+Shift+D"),
]

_TITLES = {
    "idle": "whisper-ptt: ready",
    "recording": "whisper-ptt: recording...",
    "transcribing": "whisper-ptt: transcribing...",
    "loading": "whisper-ptt: loading model...",
    "error": "whisper-ptt: error",
}


class Tray:
    def __init__(self, *, get_mode, set_mode, get_model, set_model,
                 get_log_transcripts, set_log_transcripts,
                 get_hotkey, set_hotkey,
                 on_open_config, on_quit):
        self._get_mode = get_mode
        self._set_mode = set_mode
        self._get_model = get_model
        self._set_model = set_model
        self._get_log_transcripts = get_log_transcripts
        self._set_log_transcripts = set_log_transcripts
        self._get_hotkey = get_hotkey
        self._set_hotkey = set_hotkey
        self._on_open_config = on_open_config
        self._on_quit = on_quit
        self._state = "loading"
        self.icon = pystray.Icon(
            "whisper-ptt",
            icon=make_icon(self._state),
            title=_TITLES[self._state],
            menu=self._build_menu(),
        )

    def _build_menu(self) -> Menu:
        def mode_item(value, label):
            return MenuItem(
                label,
                lambda icon, item: self._set_mode(value),
                checked=lambda item, v=value: self._get_mode() == v,
                radio=True,
            )

        def model_item(value, label):
            return MenuItem(
                label,
                lambda icon, item: self._set_model(value),
                checked=lambda item, v=value: self._get_model() == v,
                radio=True,
            )

        def hotkey_item(value, label):
            return MenuItem(
                label,
                lambda icon, item, v=value: self._set_hotkey(v),
                checked=lambda item, v=value: self._get_hotkey() == v,
                radio=True,
            )

        # A chord set by hand in the config that isn't in the curated list
        # still shows (and stays checked) as its own entry.
        hotkey_entries = [hotkey_item(v, label) for v, label in _HOTKEY_CHOICES]
        current = self._get_hotkey()
        if current not in {v for v, _ in _HOTKEY_CHOICES}:
            hotkey_entries.insert(0, hotkey_item(current, f"{current} (from config)"))

        return Menu(
            MenuItem("Mode", Menu(
                mode_item("ptt", "Push-to-talk"),
                mode_item("toggle", "Toggle"),
            )),
            MenuItem("Model", Menu(
                model_item("base.en", "base.en (fast)"),
                model_item("small.en", "small.en (accurate)"),
            )),
            MenuItem("Settings", Menu(
                MenuItem("Hotkey", Menu(*hotkey_entries)),
                MenuItem(
                    "Log transcripts",
                    lambda icon, item: self._set_log_transcripts(
                        not self._get_log_transcripts()),
                    checked=lambda item: self._get_log_transcripts(),
                ),
            )),
            Menu.SEPARATOR,
            MenuItem("Open config", lambda icon, item: self._on_open_config()),
            MenuItem("Quit", self._quit),
        )

    def _quit(self, icon, item):  # noqa: ANN001
        self._on_quit()
        icon.stop()

    def set_state(self, state: str) -> None:
        self._state = state
        try:
            self.icon.icon = make_icon(state)
            self.icon.title = _TITLES.get(state, "whisper-ptt")
        except Exception:  # noqa: BLE001 — icon not visible yet during startup
            log.debug("set_state(%s) before icon ready", state)

    def run(self) -> None:
        """Blocks on the tray message loop (call on the main thread)."""
        self.icon.run()
