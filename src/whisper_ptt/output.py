"""Emit a transcript into the focused window + leave it on the clipboard."""

from __future__ import annotations

import logging
import threading
import time

import pyperclip
from pynput.keyboard import Controller, Key

from .config import Config
from . import sendinput

log = logging.getLogger("whisper_ptt.output")


class OutputEmitter:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._kbd = Controller()

    def emit(self, text: str) -> None:
        text = text.strip()
        if not text:
            log.info("empty transcript; nothing to emit")
            return

        prev = None
        if self.cfg.restore_clipboard:
            try:
                prev = pyperclip.paste()
            except Exception:  # noqa: BLE001
                prev = None

        # Hard requirement: the transcript is always placed on the clipboard.
        # A transient clipboard lock (Office, clipboard managers, RDP) must NOT
        # crash emit — that would flip the whole engine to "error" and silently
        # lose the just-transcribed text.
        copied = self._copy_with_retry(text)

        mode = self.cfg.output_mode
        if mode == "clipboard-only":
            if copied:
                log.info("clipboard-only: %d chars on clipboard", len(text))
            else:
                log.error("clipboard-only: clipboard write failed; nothing delivered")
            return  # leave text on clipboard; never restore in this mode

        if mode == "type":
            sendinput.send_unicode(text)
            log.info("typed %d chars via SendInput", len(text))
        elif copied:  # "paste"
            time.sleep(self.cfg.paste_settle_ms / 1000.0)
            self._ctrl_v()
            log.info("pasted %d chars via Ctrl+V", len(text))
        else:  # paste requested but clipboard write failed — still deliver
            log.warning("paste: clipboard write failed; delivering via SendInput instead")
            sendinput.send_unicode(text)

        if self.cfg.restore_clipboard and prev is not None and copied:
            self._restore_later(prev)

    def _copy_with_retry(self, text: str, attempts: int = 5, delay: float = 0.02) -> bool:
        """pyperclip.copy with a short bounded retry; returns success.

        OpenClipboard contention clears in tens of ms, so a few retries almost
        always win. Never raises — a persistent failure is logged and reported
        so the caller can fall back rather than crashing the worker.
        """
        for i in range(attempts):
            try:
                pyperclip.copy(text)
                return True
            except Exception:  # noqa: BLE001
                if i == attempts - 1:
                    log.exception("clipboard copy failed after %d attempts", attempts)
                    return False
                time.sleep(delay)
        return False

    def _ctrl_v(self) -> None:
        self._kbd.press(Key.ctrl)
        self._kbd.press("v")
        self._kbd.release("v")
        self._kbd.release(Key.ctrl)

    def _restore_later(self, prev: str) -> None:
        def _restore():
            time.sleep(self.cfg.restore_delay_ms / 1000.0)
            try:
                pyperclip.copy(prev)
            except Exception:  # noqa: BLE001
                log.debug("clipboard restore failed")
        threading.Thread(target=_restore, daemon=True).start()
