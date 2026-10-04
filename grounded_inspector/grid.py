"""Coordinate-grid overlay for the INPUT image, to tighten bbox localization.

A vision model ESTIMATES bbox coordinates and is imprecise at exact edges (it may put a
box's left edge at 0.40 when the defect really starts at 0.47). Attaching a copy of the
input with a LABELED 0..1 coordinate grid lets the model READ each box edge off the
nearest gridline instead of guessing a fraction. The clean input is still attached too,
so a gridline never hides a faint defect - the grid copy is only a coordinate ruler.
"""
from __future__ import annotations

import os
import tempfile

from PIL import Image, ImageDraw, ImageFont, ImageOps


def _font(size: int):
    for n in ("arialbd.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(n, size)
        except Exception:  # noqa
            continue
    return ImageFont.load_default()


def grid_for(image_path: str, major: float = 0.10, minor: float = 0.05):
    """Write a labeled coordinate-grid copy of `image_path` to a temp PNG and return its
    path (or None on failure). Major magenta lines every `major` (labeled 0.00..1.00 for
    x along the top and y down the left); minor cyan lines every `minor`."""
    try:
        img = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
    except Exception:  # noqa
        return None
    W, H = img.size
    d = ImageDraw.Draw(img)
    fb = _font(max(11, int(min(W, H) * 0.022)))
    sx, sy = max(1, int(W * minor)), max(1, int(H * minor))
    for i in range(0, W + 1, sx):
        d.line([(i, 0), (i, H)], fill=(0, 200, 255), width=1)
    for j in range(0, H + 1, sy):
        d.line([(0, j), (W, j)], fill=(0, 200, 255), width=1)
    mx, my = max(1, int(W * major)), max(1, int(H * major))
    for i in range(0, W + 1, mx):
        d.line([(i, 0), (i, H)], fill=(255, 0, 255), width=1)
        d.text((i + 2, 2), f"{i / W:.2f}", fill=(255, 0, 255), font=fb)
    for j in range(0, H + 1, my):
        d.line([(0, j), (W, j)], fill=(255, 0, 255), width=1)
        d.text((2, j + 2), f"{j / H:.2f}", fill=(255, 0, 255), font=fb)
    out = os.path.join(tempfile.gettempdir(),
                       os.path.splitext(os.path.basename(image_path))[0] + "_gridref.png")
    try:
        img.save(out)
    except Exception:  # noqa
        return None
    return out
