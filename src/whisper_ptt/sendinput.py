"""ctypes SendInput wrapper for Unicode keystroke injection (Windows).

Used by the "type" output mode. KEYEVENTF_UNICODE injects arbitrary Unicode
independent of keyboard layout; surrogate pairs are emitted as two units so
astral-plane characters (emoji) work too.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1

ULONG_PTR = ctypes.c_size_t

# Bind with use_last_error so ctypes.get_last_error() reflects the real Win32
# error after SendInput (the default WinDLL does not capture it).
_user32 = ctypes.WinDLL("user32", use_last_error=True)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    # Present only so sizeof(INPUT) matches the canonical Win32 layout (the
    # union is sized by its largest member); SendInput requires the exact size.
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]


def _unit(code_unit: int, key_up: bool) -> INPUT:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if key_up else 0)
    ki = KEYBDINPUT(wVk=0, wScan=code_unit, dwFlags=flags, time=0, dwExtraInfo=0)
    return INPUT(type=INPUT_KEYBOARD, u=_INPUTunion(ki=ki))


def send_unicode(text: str) -> None:
    """Type `text` into the focused window via synthetic Unicode keystrokes."""
    if not text:
        return
    events: list[INPUT] = []
    for ch in text:
        cp = ord(ch)
        if cp > 0xFFFF:  # encode as a UTF-16 surrogate pair
            cp -= 0x10000
            for unit in (0xD800 + (cp >> 10), 0xDC00 + (cp & 0x3FF)):
                events.append(_unit(unit, False))
                events.append(_unit(unit, True))
        else:
            events.append(_unit(cp, False))
            events.append(_unit(cp, True))

    n = len(events)
    arr = (INPUT * n)(*events)
    sent = _user32.SendInput(n, arr, ctypes.sizeof(INPUT))
    if sent != n:
        raise ctypes.WinError(ctypes.get_last_error())
