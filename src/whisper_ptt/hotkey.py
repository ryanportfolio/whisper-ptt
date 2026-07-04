"""Global hotkey via a pynput low-level keyboard hook.

Supports push-to-talk (fires on full-chord press AND release) and toggle.
Callbacks are kept trivial (they only enqueue work) so the hook handler never
exceeds the Windows LowLevelHooksTimeout and gets dropped.

For a SINGLE printable-key hotkey (e.g. the backtick `), the key is also a
normal typing character, so the hook selectively SUPPRESSES it system-wide
while the app runs — otherwise every toggle-tap would leak the character into
the focused window. Suppression only applies to single-key hotkeys; chords with
modifiers are never suppressed (we must not swallow Ctrl/Alt globally).
"""

from __future__ import annotations

import logging
import sys
import time

from pynput import keyboard

log = logging.getLogger("whisper_ptt.hotkey")

# Canonicalize modifier variants to a single token.
_MODIFIER_TOKENS = {
    keyboard.Key.ctrl: "ctrl", keyboard.Key.ctrl_l: "ctrl", keyboard.Key.ctrl_r: "ctrl",
    keyboard.Key.alt: "alt", keyboard.Key.alt_l: "alt", keyboard.Key.alt_r: "alt",
    keyboard.Key.alt_gr: "alt",
    keyboard.Key.shift: "shift", keyboard.Key.shift_l: "shift", keyboard.Key.shift_r: "shift",
    keyboard.Key.cmd: "win", keyboard.Key.cmd_l: "win", keyboard.Key.cmd_r: "win",
}

# Aliases accepted in the config chord string. Canonical values MUST match what
# _normalize_key() returns at runtime (i.e. pynput Key.<name>).
_ALIASES = {
    "control": "ctrl", "ctl": "ctrl",
    "option": "alt", "opt": "alt",
    "super": "win", "cmd": "win", "windows": "win", "meta": "win",
    "escape": "esc", "return": "enter", "spacebar": "space", "backtick": "`",
    "grave": "`", "capslock": "caps_lock",
}

# vk -> letter, for when Ctrl is held and pynput reports a control char.
_VK_LETTER = {vk: chr(ord("a") + vk - 0x41) for vk in range(0x41, 0x5B)}

# canonical token -> Windows virtual-key code, for selective suppression.
_TOKEN_VK: dict[str, int] = {chr(ord("a") + i): 0x41 + i for i in range(26)}
_TOKEN_VK.update({str(d): 0x30 + d for d in range(10)})
_TOKEN_VK.update({f"f{n}": 0x6F + n for n in range(1, 25)})  # f1..f24 -> 0x70..
_TOKEN_VK.update({
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC,
    ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
    "space": 0x20, "tab": 0x09, "enter": 0x0D, "esc": 0x1B,
    "backspace": 0x08, "caps_lock": 0x14,
    # navigation / editing keys (pynput Key.<name>)
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "page_up": 0x21, "page_down": 0x22,
    "insert": 0x2D, "delete": 0x2E, "num_lock": 0x90, "scroll_lock": 0x91,
    "print_screen": 0x2C, "pause": 0x13, "menu": 0x5D,
})


def _normalize_key(key) -> str | None:
    """Map a pynput key event to a canonical chord token."""
    if key in _MODIFIER_TOKENS:
        return _MODIFIER_TOKENS[key]
    if isinstance(key, keyboard.Key):
        return key.name  # e.g. "space", "f9", "enter"
    # KeyCode
    vk = getattr(key, "vk", None)
    ch = getattr(key, "char", None)
    if ch and ch.isprintable() and len(ch) == 1 and ord(ch) >= 32:
        return ch.lower()
    if vk in _VK_LETTER:  # ctrl held -> char is a control code; recover via vk
        return _VK_LETTER[vk]
    if ch:
        return ch.lower()
    return None


def parse_chord(chord: str) -> frozenset[str]:
    tokens = set()
    for raw in chord.lower().replace("-", "+").split("+"):
        t = raw.strip()
        if not t:
            continue
        tokens.add(_ALIASES.get(t, t))
    if not tokens:
        raise ValueError(f"empty/invalid hotkey chord: {chord!r}")
    return frozenset(tokens)


class HotkeyController:
    """Watches the keyboard for a chord; drives on_press/on_release callbacks.

    on_press fires once when the full chord becomes pressed.
    on_release fires once when the chord stops being fully pressed.
    """

    def __init__(self, chord: str, on_press, on_release,
                 debounce_ms: int = 50, suppress: bool = True):
        self.chord = parse_chord(chord)
        self._on_press = on_press
        self._on_release = on_release
        self._debounce_ms = max(0, int(debounce_ms))
        self._down: set[str] = set()
        self._active = False
        self._last_activate = 0.0
        self._listener: keyboard.Listener | None = None
        self._suppress_vks = self._compute_suppress_vks() if suppress else set()

    def _compute_suppress_vks(self) -> set[int]:
        # Only suppress a single, printable, non-modifier key.
        if sys.platform != "win32" or len(self.chord) != 1:
            return set()
        tok = next(iter(self.chord))
        vk = _TOKEN_VK.get(tok)
        return {vk} if vk is not None else set()

    def start(self) -> None:
        kwargs = dict(on_press=self._handle_press, on_release=self._handle_release)
        if self._suppress_vks:
            kwargs["win32_event_filter"] = self._win32_filter
        self._listener = keyboard.Listener(**kwargs)
        self._listener.start()
        log.info("hotkey listening for chord: %s%s", "+".join(sorted(self.chord)),
                 " (suppressed)" if self._suppress_vks else "")

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    # ---- selective system-wide suppression --------------------------------
    def _win32_filter(self, msg, data) -> bool:
        """Selectively suppress only the hotkey key, system-wide.

        pynput's hook proc suppresses an event ONLY if it raises
        SuppressException, which it does iff the listener's ``_suppress`` flag is
        set when the event is handled (``_util/win32.py``). The filter's return
        value merely gates processing via an ``is False`` check, so we set
        ``_suppress`` per-event and return True (pass-through): matching keys get
        suppressed, every other key reaches the OS normally.
        """
        lst = self._listener
        if lst is not None:
            try:
                lst._suppress = data.vkCode in self._suppress_vks
            except AttributeError:
                pass
        return True

    # ---- chord tracking ---------------------------------------------------
    def _chord_down(self) -> bool:
        return self.chord.issubset(self._down)

    def _handle_press(self, key, injected: bool = False) -> None:
        # Ignore the app's OWN synthetic keystrokes (Ctrl+V paste / "type" mode
        # SendInput). pynput passes `injected` as the 2nd positional arg on
        # Windows; without this, emitting a transcript that contains the hotkey
        # character re-fires the chord mid-emit and starts a spurious recording.
        if injected:
            return
        tok = _normalize_key(key)
        if tok is None:
            return
        self._down.add(tok)
        if not self._active and self._chord_down():
            now = time.monotonic()
            if (now - self._last_activate) * 1000.0 < self._debounce_ms:
                return  # debounce: ignore chattering / too-fast re-trigger
            self._last_activate = now
            self._active = True
            try:
                self._on_press()
            except Exception:  # noqa: BLE001 — never let a callback kill the hook
                log.exception("on_press callback error")

    def _handle_release(self, key, injected: bool = False) -> None:
        if injected:
            return
        tok = _normalize_key(key)
        if tok is None:
            return
        self._down.discard(tok)
        if self._active and not self._chord_down():
            self._active = False
            try:
                self._on_release()
            except Exception:  # noqa: BLE001
                log.exception("on_release callback error")
