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

pyinstaller --noconfirm --clean --windowed \
  --name "${APP_NAME}" \
  --distpath "${ROOT}/dist" \
  --workpath "${WORK_DIR}" \
  --specpath "${ROOT}" \
  --icon "${APP_ICON}" \
  --add-data "tray-icon.ico:." \
  --add-data "tray-icon.png:." \
  --add-data "VERSION:." \
  --add-data "macos_menubar_helper.py:." \
  --add-data "macos/privileged/wg-helper.sh:macos/privileged" \
  --add-data "macos/privileged/install_privileges.sh:macos/privileged" \
  --hidden-import config \
  --hidden-import tunnel \
  --hidden-import ui \
  --hidden-import macos_tray \
  --hidden-import notifications \
  --hidden-import platform_utils \
  --hidden-import teleport \
  --hidden-import objc \
  --hidden-import AppKit \
  --hidden-import Foundation \
  --hidden-import UserNotifications \
  --hidden-import PyObjCTools \
  --hidden-import PySide6.QtCore \
  --hidden-import PySide6.QtGui \
  --hidden-import PySide6.QtWidgets \
  --collect-all PySide6 \
  main.py

rm -f "${ROOT}/${APP_NAME}.spec"

# Menu-bar accessory: no Dock icon for the packaged .app
INFO_PLIST="${ROOT}/dist/${APP_NAME}.app/Contents/Info.plist"
if [[ -f "${INFO_PLIST}" ]]; then
  if /usr/libexec/PlistBuddy -c "Print :LSUIElement" "${INFO_PLIST}" >/dev/null 2>&1; then
    /usr/libexec/PlistBuddy -c "Set :LSUIElement true" "${INFO_PLIST}"
  else
    /usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "${INFO_PLIST}"
  fi
  APP_VERSION="$(tr -d '[:space:]' < "${ROOT}/VERSION")"
  if /usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "${INFO_PLIST}" >/dev/null 2>&1; then
    /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString ${APP_VERSION}" "${INFO_PLIST}"
  else
    /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string ${APP_VERSION}" "${INFO_PLIST}"
  fi
  if /usr/libexec/PlistBuddy -c "Print :CFBundleVersion" "${INFO_PLIST}" >/dev/null 2>&1; then
    /usr/libexec/PlistBuddy -c "Set :CFBundleVersion ${APP_VERSION}" "${INFO_PLIST}"
  else
    /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string ${APP_VERSION}" "${INFO_PLIST}"
  fi
  echo "Set LSUIElement=true and version=${APP_VERSION} in Info.plist"
fi

echo ""
echo "Built: dist/${APP_NAME}.app"
echo "Next: ./build_macos_dmg.sh --skip-app-build"
