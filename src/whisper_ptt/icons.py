"""Procedurally-drawn tray icons (no .ico assets shipped)."""

from __future__ import annotations

from PIL import Image, ImageDraw

# state -> accent color
_COLORS = {
    "idle": (120, 120, 130),
    "recording": (220, 50, 50),
    "transcribing": (235, 170, 30),
    "loading": (90, 130, 220),
    "error": (150, 20, 20),
}

_SIZE = 64


def make_icon(state: str) -> Image.Image:
    color = _COLORS.get(state, _COLORS["idle"])
    img = Image.new("RGBA", (_SIZE, _SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Filled background disc
    d.ellipse((2, 2, _SIZE - 2, _SIZE - 2), fill=(30, 30, 36, 255))

    # Mic body (rounded capsule)
    cx = _SIZE // 2
    d.rounded_rectangle((cx - 9, 14, cx + 9, 40), radius=9, fill=color)
    # Mic stand arc
    d.arc((cx - 15, 22, cx + 15, 48), start=20, end=160, fill=color, width=4)
    # Stem + base
    d.line((cx, 48, cx, 54), fill=color, width=4)
    d.line((cx - 8, 54, cx + 8, 54), fill=color, width=4)
    return img
