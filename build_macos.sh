#!/usr/bin/env bash
# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)
#
# Build a macOS .app bundle with PyInstaller.
# For the full installer DMG (WireGuard auto-install, same as Windows Inno), use:
#   ./build_macos_dmg.sh
#
# Prerequisites:
#   python3 -m venv .venv && source .venv/bin/activate
#   pip install -r requirements.txt
#
# Usage:
#   ./build_macos.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

WORK_DIR="${ROOT}/build/pyinstaller_app"
APP_NAME="AmpliFi Teleport for Desktop"

rm -rf "${WORK_DIR}"
rm -rf "${ROOT}/dist/${APP_NAME}.app"
rm -f "${ROOT}/${APP_NAME}.spec"

ICON_ICO="${ROOT}/tray-icon.ico"
ICON_PNG="${ROOT}/tray-icon.png"

if [[ ! -f "${ICON_ICO}" ]]; then
  echo "ERROR: Missing ${ICON_ICO}" >&2
  exit 1
fi

# Ensure PNG exists (needed for macOS tray / window icons)
if [[ ! -f "${ICON_PNG}" ]]; then
  echo "Generating tray-icon.png from tray-icon.ico..."
  python3 - <<'PY'
from PIL import Image
img = Image.open("tray-icon.ico")
frames = []
try:
    i = 0
    while True:
        img.seek(i)
        frames.append(img.copy().convert("RGBA"))
        i += 1
except EOFError:
    pass
best = max(frames, key=lambda im: im.size[0] * im.size[1]) if frames else img.convert("RGBA")
best.save("tray-icon.png")
print("Wrote tray-icon.png", best.size)
PY
fi

# Prefer a real .icns for the .app bundle icon (PyInstaller / macOS expectation)
ICON_ICNS="${WORK_DIR}/tray-icon.icns"
mkdir -p "${WORK_DIR}/icon.iconset"
python3 - <<'PY'
from PIL import Image
from pathlib import Path

src = Image.open("tray-icon.png").convert("RGBA")
out = Path("build/pyinstaller_app/icon.iconset")
sizes = [16, 32, 64, 128, 256, 512]
for size in sizes:
    resized = src.resize((size, size), Image.Resampling.LANCZOS)
    resized.save(out / f"icon_{size}x{size}.png")
    resized2 = src.resize((size * 2, size * 2), Image.Resampling.LANCZOS)
    resized2.save(out / f"icon_{size}x{size}@2x.png")
print("Wrote iconset")
PY

if command -v iconutil >/dev/null 2>&1; then
  iconutil -c icns "${WORK_DIR}/icon.iconset" -o "${ICON_ICNS}"
  APP_ICON="${ICON_ICNS}"
else
  echo "WARNING: iconutil not found; falling back to PNG app icon"
  APP_ICON="${ICON_PNG}"
fi

# IMPORTANT: keep --specpath at the project root.
# PyInstaller resolves --add-data sources relative to the .spec location.
# Putting the spec under build/pyinstaller_app made it look for:
#   build/pyinstaller_app/tray-icon.ico
pyinstaller --noconfirm --clean --windowed \
  --name "${APP_NAME}" \
  --distpath "${ROOT}/dist" \
  --workpath "${WORK_DIR}" \
  --specpath "${ROOT}" \
  --icon "${APP_ICON}" \
  --add-data "tray-icon.ico:." \
  --add-data "tray-icon.png:." \
  --hidden-import config \
  --hidden-import tunnel \
  --hidden-import ui \
  --hidden-import notifications \
  --hidden-import platform_utils \
  --hidden-import teleport \
  --hidden-import macos_tray \
  --hidden-import plyer.platforms.darwin.notification \
  --hidden-import AppKit \
  --hidden-import Foundation \
  main.py

# Clean generated spec from repo root (kept out of git via *.spec)
rm -f "${ROOT}/${APP_NAME}.spec"

echo ""
echo "Built: dist/${APP_NAME}.app"
echo "Next: ./build_macos_dmg.sh --skip-app-build   # creates Setup .dmg with WireGuard auto-install"
