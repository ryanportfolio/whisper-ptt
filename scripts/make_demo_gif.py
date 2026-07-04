"""Generate docs/demo.gif — a stylized animation of the dictation flow.

The GIF is an illustration (not a screen capture): a mock editor window plus
the app's real tray icons (drawn by whisper_ptt.icons) stepping through
idle -> record -> transcribe -> paste. Regenerate with:

    uv run --no-project --with pillow python scripts/make_demo_gif.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from whisper_ptt.icons import make_icon  # noqa: E402

W, H = 640, 400
FRAME_MS = 100

BG = (21, 21, 26)
EDITOR_BG = (30, 30, 37)
EDITOR_BORDER = (52, 52, 62)
TITLEBAR = (42, 42, 51)
TASKBAR = (29, 29, 36)
TEXT = (216, 216, 224)
DIM = (154, 154, 168)
FAINT = (90, 90, 104)
REC = (220, 50, 50)
TRN = (235, 170, 30)
OK = (40, 200, 64)
ACCENT = (90, 130, 220)

PASTE_LINES = [
    "Dictated with whisper-ptt: fully offline,",
    "no cloud, no account - straight into",
    "whatever window is focused.",
]


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


F_UI = _font("segoeui.ttf", 16)
F_UI_SM = _font("segoeui.ttf", 13)
F_MONO = _font("consola.ttf", 17)


def _base_frame(state: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Editor window
    d.rounded_rectangle((24, 20, 616, 296), radius=10, fill=EDITOR_BG,
                        outline=EDITOR_BORDER, width=1)
    d.rounded_rectangle((24, 20, 616, 54), radius=10, fill=TITLEBAR)
    d.rectangle((24, 40, 616, 54), fill=TITLEBAR)
    d.text((44, 27), "meeting-notes.txt", font=F_UI_SM, fill=DIM)
    d.text((556, 25), "─  □  ✕", font=F_UI_SM, fill=FAINT)

    # Taskbar with tray corner
    d.rectangle((0, 352, W, H), fill=TASKBAR)
    d.line((0, 352, W, 352), fill=EDITOR_BORDER, width=1)
    for i in range(3):  # abstract pinned apps
        d.rounded_rectangle((18 + i * 40, 364, 42 + i * 40, 388),
                            radius=6, fill=(45, 45, 55))
    d.text((596, 368), "9:41", font=F_UI_SM, fill=DIM)

    # The app's real tray icon for this state
    icon = make_icon(state).resize((28, 28), Image.LANCZOS)
    img.paste(icon, (556, 362), icon)
    return img, d


def _keycap(d: ImageDraw.ImageDraw, x: int, y: int, pressed: bool) -> int:
    """Draw the backtick keycap; returns its right edge."""
    fill = ACCENT if pressed else (48, 48, 58)
    dy = 1 if pressed else 0
    d.rounded_rectangle((x, y + dy, x + 26, y + 26 + dy), radius=6, fill=fill,
                        outline=(90, 90, 110), width=1)
    d.text((x + 13, y + 12 + dy), "`", font=F_UI, fill=TEXT, anchor="mm")
    return x + 26


def _caption_tap(d: ImageDraw.ImageDraw, pressed: bool, verb: str) -> None:
    y = 312
    total = int(d.textlength(f"tap    {verb}", font=F_UI)) + 26 + 16
    x = (W - total) // 2
    d.text((x, y + 13), "tap", font=F_UI, fill=DIM, anchor="lm")
    x += int(d.textlength("tap", font=F_UI)) + 8
    x = _keycap(d, x, y, pressed) + 8
    d.text((x, y + 13), verb, font=F_UI, fill=DIM, anchor="lm")


def _caption_center(d: ImageDraw.ImageDraw, text: str, color) -> None:
    d.text((W // 2, 325), text, font=F_UI, fill=color, anchor="mm")


def _waveform(d: ImageDraw.ImageDraw, t: int) -> None:
    cx = W // 2
    for b in range(-8, 9):
        h = 4 + 11 * abs(math.sin(0.9 * t + 0.8 * b))
        x = cx + b * 9
        d.line((x, 325 - h, x, 325 + h), fill=REC, width=4)


def _editor_text(d: ImageDraw.ImageDraw, lines: list[str],
                 cursor_on: bool, highlight: bool) -> None:
    x, y0, lh = 44, 72, 26
    for i, line in enumerate(lines):
        if highlight and line:
            wpx = d.textlength(line, font=F_MONO)
            d.rectangle((x - 2, y0 + i * lh - 2, x + wpx + 2, y0 + i * lh + 20),
                        fill=(60, 75, 120))
        d.text((x, y0 + i * lh), line, font=F_MONO, fill=TEXT)
    if cursor_on:
        i = max(0, len(lines) - 1)
        cx = x + (d.textlength(lines[-1], font=F_MONO) if lines else 0)
        d.rectangle((cx + 1, y0 + i * lh, cx + 3, y0 + i * lh + 19), fill=TEXT)


def build_frames() -> list[Image.Image]:
    frames: list[Image.Image] = []

    def add(state: str, caption, *, text=(), cursor=True, highlight=False, n=1):
        for k in range(n):
            img, d = _base_frame(state)
            _editor_text(d, list(text), cursor and (len(frames) + k) % 6 < 3,
                         highlight)
            caption(d, len(frames))
            frames.append(img)

    # 1. idle — invite the tap
    add("idle", lambda d, t: _caption_tap(d, False, "to dictate"), n=8)
    # 2. tap down
    add("idle", lambda d, t: _caption_tap(d, True, "to dictate"), n=2)
    # 3. recording — waveform
    add("recording", lambda d, t: _waveform(d, t), n=16)
    # 4. tap again to stop
    add("recording", lambda d, t: _caption_tap(d, True, "to stop"), n=2)
    # 5. transcribing on CPU
    for k in range(12):
        dots = "." * (1 + k // 3 % 3)
        add("transcribing",
            lambda d, t, s=f"transcribing on CPU{dots}": _caption_center(d, s, TRN))
    # 6. paste lands — brief selection highlight, then hold
    add("idle", lambda d, t: _caption_center(
        d, "pasted into the focused window", OK),
        text=PASTE_LINES, highlight=True, n=2)
    add("idle", lambda d, t: _caption_center(
        d, "pasted into the focused window  (and on your clipboard)", OK),
        text=PASTE_LINES, n=20)
    return frames


def main() -> int:
    out = ROOT / "docs" / "demo.gif"
    out.parent.mkdir(parents=True, exist_ok=True)
    frames = build_frames()
    frames[0].save(
        out, save_all=True, append_images=frames[1:],
        duration=FRAME_MS, loop=0, optimize=True,
    )
    print(f"wrote {out} ({len(frames)} frames, {out.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
