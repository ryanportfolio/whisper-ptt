# whisper-ptt settings/status window — design

Date: 2026-07-05
Status: approved (user delegated all decisions, "go with your recommendations")

## Problem

whisper-ptt is tray-only. Field testing surfaced three failures that a visible
window would have prevented or made obvious:

1. **No device control.** The app followed the Windows default input and once
   latched onto an *output* device ("Realtek Digital Output"), capturing zero
   audio. The user had no in-app way to pick a microphone and had to hand-edit
   `config.toml` and reason about unstable PortAudio indices.
2. **Invisible failures.** The windowed exe has no console, so `no audio
   captured` and `model not installed` only reached the swallowed log file. The
   user saw a dictation that silently produced nothing.
3. **"Nothing happens on launch."** A tray-only app reads as "didn't start,"
   and confuses input (mic) vs output (earphone) devices.

Goal: a small, professional settings/status window that makes state visible and
lets the user pick their mic, model, mode, and hotkey — without losing the
lightweight background-utility nature (global hotkey must keep working).

## Decisions

- **Toolkit: tkinter + ttk.** Standard library (no new pinned dependency —
  honors the "ask before adding runtime deps" rule), already present with the
  pinned CPython 3.11, and bundles cleanly with PyInstaller. `ttk` themed
  widgets give an acceptable native-ish look. Heavier toolkits (PySide/PyQt)
  are rejected: large bundle, licensing, overkill for a handful of controls.
- **Window model:** the window shows on launch and minimizes to the tray on
  close (`WM_DELETE_WINDOW` → `withdraw`), staying resident. The tray gains a
  "Show whisper-ptt" action (`deiconify`). Quit lives on both the window and the
  tray. This matches the user's "a panel when opening the exe" while keeping the
  background utility.
- **Threading:** tkinter must own the main thread and its own `mainloop`, which
  blocks — as does pystray's `icon.run()`. Resolution: the **window runs on the
  main thread**; the **tray runs detached** via `pystray.Icon.run_detached()`
  (supported on the win32 backend). The engine worker/hotkey/audio/boot threads
  are unchanged. All engine→window updates are marshaled onto the tk loop with
  `root.after(...)`; tkinter is not thread-safe and must never be touched from
  the worker thread directly.

## Architecture

New module `src/whisper_ptt/window.py`, class `SettingsWindow`, constructed with
the same getter/setter callbacks the `Tray` already takes, plus a few new ones.
It never imports the engine; it talks through callables (same seam as `Tray`),
so it stays independently testable (construct it, assert widgets realize) exactly
like `tests/test_tray_menu.py`.

`app.py main()` becomes:

```
engine = Engine(cfg)
tray   = Tray(...)                      # run_detached() in a background thread
window = SettingsWindow(root, ...)      # owns the tk root
engine.tray, engine.window = tray, window
engine.start_worker(); engine.hotkey.start()
Thread(boot).start()
tray.icon.run_detached()
root.mainloop()                         # blocks on the main thread
```

`Engine` gains:
- `set_device(index_or_none)` — enqueue a worker command that stops any capture,
  `audio.close()`, sets `cfg.device_index`, `audio.open()`, persists; on failure
  reverts to the previous device and reports via the status sink. Device
  validation already lives in `AudioCapture._resolve_device`.
- `monitor_mic(on)` — worker command that gates `audio.start()/stop()` WITHOUT
  transcribing, so the window can poll `engine.audio.rms` for a live level meter
  during a mic test. Guarded so it can't run while recording.
- A **status sink**: the engine already calls `_set_state(state)`; extend it to
  also notify the window (marshaled) and to publish a "last result" string
  ("42 chars pasted", "no audio captured", "model small.en not installed").

`Tray` change: add a "Show whisper-ptt" item that calls an `on_show` callback;
keep the existing Mode/Model/Settings items (they and the window both drive the
same engine setters and read the same engine state, so they stay consistent).

## Window layout (sections, top to bottom)

1. **Status** — a colored state chip (Ready / Recording… / Transcribing… /
   Loading… / Error) + labels for model, hotkey, mode, and a "Last:" result
   line. Updated by `root.after` poll (~150 ms) of engine state.
2. **Microphone** — `ttk.Combobox` of "System default" + each input device from
   `list_input_devices()`. Changing it calls `set_device`. A **Test** button
   runs `monitor_mic(True)` for ~3 s, drives a `ttk.Progressbar` from the live
   RMS, then reports "Mic OK" or "No/low signal", and `monitor_mic(False)`.
3. **Speech model** — `ttk.Combobox` of base.en / small.en, each tagged
   "(installed)" or "(not installed)" via `cfg.find_local_model`. Switching to an
   installed model calls the existing model-change path. Uninstalled entries are
   shown but not selectable in v1 (download deferred).
4. **Mode** — PTT / Toggle radio buttons → `set_mode`.
5. **Hotkey** — `ttk.Combobox` of the curated chords (reusing the tray list) plus
   the current value → `set_hotkey`.
6. **Footer** — "Open config file" and "Quit".

## Error handling

- Window construction/`mainloop` must never take down the engine; wrap the tk
  bootstrap so a GUI failure still leaves the tray + hotkey working (log + tray
  notify, headless fallback).
- `set_device` failure reverts and surfaces the reason in the status line.
- All engine→UI updates go through `root.after`; direct cross-thread tk calls are
  forbidden.

## Testing / verification

- `tests/test_window.py` (framework-free, matches the others): construct the
  `SettingsWindow` against a `Tk()` root, walk the widgets so every var/label
  realizes, fire the device/mode/hotkey callbacks and assert they reach the
  stub setters, and assert the model combobox tags availability. Skips cleanly
  if `Tk()` can't init (headless CI has no display — guard with a try/except and
  print a SKIP, mirroring how audio tests are hardware-gated).
- A `--selftest-ui` flag builds the window + detached tray, pumps the loop
  briefly with `root.after(300, root.destroy)`, and exits 0 — a construction/
  threading smoke test that never hangs.
- Real look-and-feel + interaction: authoritative only on the user's Windows
  session (per CLAUDE.md). Claude verifies construction, logic, imports, and a
  brief real launch; the user confirms the actual UX.

## Out of scope (follow-ups)

- small.en **download** button (needs the fetch logic importable inside the
  frozen exe, plus progress UI and `allow_download` handling).
- Global restyle/theming beyond ttk defaults.
- Persisting window position/size.
