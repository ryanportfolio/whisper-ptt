"""Tray menu construction test: the pystray menu must build, and its radio
actions must fire with the right value.

Regression guard for a shipped startup crash: a 3-argument action lambda
(``lambda icon, item, v=value: ...``) tripped pystray's ``_assert_action``,
which rejects any action taking more than two arguments, so building the tray
raised ``ValueError`` before the icon ever appeared.

Runnable with no test framework and no network:
    uv run python tests/test_tray_menu.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from whisper_ptt.tray import Tray  # noqa: E402


def _make_tray(hotkey: str = "`"):
    state = {"mode": "ptt", "model": "base.en", "log": False, "hotkey": hotkey}
    tray = Tray(
        get_mode=lambda: state["mode"], set_mode=lambda v: state.update(mode=v),
        get_model=lambda: state["model"], set_model=lambda v: state.update(model=v),
        get_log_transcripts=lambda: state["log"],
        set_log_transcripts=lambda v: state.update(log=v),
        get_hotkey=lambda: state["hotkey"], set_hotkey=lambda v: state.update(hotkey=v),
        on_open_config=lambda: None, on_quit=lambda: None,
    )
    return tray, state


def _walk(items):
    """Yield every menu item, descending into submenus."""
    for item in items:
        yield item
        sub = item.submenu
        if sub is not None:
            yield from _walk(sub.items)


def test_menu_builds_and_realizes():
    # Construction runs pystray's _assert_action on every action; realizing
    # text/checked exercises the label and radio-state closures too.
    tray, _ = _make_tray()
    for item in _walk(tray.icon.menu.items):
        _ = item.text
        _ = item.checked
    print("ok: tray menu builds and every item realizes")


def test_hotkey_action_sets_value():
    tray, state = _make_tray(hotkey="`")
    target = next(i for i in _walk(tray.icon.menu.items) if i.text == "F9")
    target(tray.icon)  # MenuItem.__call__ -> action(icon, item)
    assert state["hotkey"] == "f9", state
    print("ok: hotkey radio action sets the selected chord")


def test_custom_hotkey_shows_from_config():
    tray, _ = _make_tray(hotkey="ctrl+shift+z")
    labels = [i.text for i in _walk(tray.icon.menu.items)]
    assert any("(from config)" in label for label in labels), labels
    print("ok: a non-curated hotkey appears as its own '(from config)' entry")


def main() -> int:
    test_menu_builds_and_realizes()
    test_hotkey_action_sets_value()
    test_custom_hotkey_shows_from_config()
    print("ALL_TRAY_TESTS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
