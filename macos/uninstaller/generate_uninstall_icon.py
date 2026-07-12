#!/usr/bin/env python3
# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)
"""Build macos/uninstaller/uninstall-icon.png from tray-icon.png + red minus badge."""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "tray-icon.png"
DEST = Path(__file__).resolve().parent / "uninstall-icon.png"


def main() -> None:
    base = Image.open(SRC).convert("RGBA")
    width, height = base.size
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    radius = max(28, int(width * 0.24))
    margin = max(8, int(width * 0.06))
    cx = width - margin - radius
    cy = height - margin - radius
    outline = max(2, width // 64)
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=(196, 45, 45, 255),
        outline=(255, 255, 255, 240),
        width=outline,
    )

    bar_w = int(radius * 1.25)
    bar_h = max(6, int(radius * 0.36))
    x0, y0 = cx - bar_w // 2, cy - bar_h // 2
    x1, y1 = cx + bar_w // 2, cy + bar_h // 2
    try:
        draw.rounded_rectangle(
            [x0, y0, x1, y1], radius=bar_h // 2, fill=(255, 255, 255, 255)
        )
    except AttributeError:
        draw.rectangle([x0, y0, x1, y1], fill=(255, 255, 255, 255))

    out = Image.alpha_composite(base, overlay)
    out.save(DEST, optimize=True)
    print(f"Wrote {DEST.relative_to(ROOT)} ({out.size[0]}x{out.size[1]})")


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
