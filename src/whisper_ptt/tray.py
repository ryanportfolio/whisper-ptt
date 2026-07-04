"""System-tray UI (pystray): state icon + menu."""

from __future__ import annotations

import logging

import pystray
from pystray import Menu, MenuItem

from .icons import make_icon

log = logging.getLogger("whisper_ptt.tray")

_TITLES = {
    "idle": "whisper-ptt: ready",
    "recording": "whisper-ptt: recording...",
    "transcribing": "whisper-ptt: transcribing...",
    "loading": "whisper-ptt: loading model...",
    "error": "whisper-ptt: error",
}


class Tray:
    def __init__(self, *, get_mode, set_mode, get_model, set_model,
                 on_open_config, on_quit):
        self._get_mode = get_mode
        self._set_mode = set_mode
        self._get_model = get_model
        self._set_model = set_model
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

        return Menu(
            MenuItem("Mode", Menu(
                mode_item("ptt", "Push-to-talk"),
                mode_item("toggle", "Toggle"),
            )),
            MenuItem("Model", Menu(
                model_item("base.en", "base.en (fast)"),
                model_item("small.en", "small.en (accurate)"),
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
