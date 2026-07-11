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

rm -rf build/pyinstaller_app dist/*.app 2>/dev/null || true
# Keep dist/*.dmg / dist/*.pkg if present; only replace the app bundle below
rm -rf "dist/AmpliFi Teleport for Desktop.app"

# Paths must be absolute: with --specpath, PyInstaller resolves --add-data / --icon
# relative to the spec directory (not the project root).
ICON_PNG="${ROOT}/tray-icon.png"
ICON_ICO="${ROOT}/tray-icon.ico"

if [[ ! -f "$ICON_PNG" ]]; then
  echo "ERROR: Missing ${ICON_PNG}" >&2
  exit 1
fi
if [[ ! -f "$ICON_ICO" ]]; then
  echo "ERROR: Missing ${ICON_ICO}" >&2
  exit 1
fi

# On macOS, --add-data uses colon separators
pyinstaller --noconfirm --windowed --name "AmpliFi Teleport for Desktop" \
  --distpath dist \
  --workpath build/pyinstaller_app \
  --specpath build/pyinstaller_app \
  --icon "$ICON_PNG" \
  --add-data "${ICON_ICO}:." \
  --add-data "${ICON_PNG}:." \
  --hidden-import config \
  --hidden-import tunnel \
  --hidden-import ui \
  --hidden-import notifications \
  --hidden-import platform_utils \
  --hidden-import teleport \
  --hidden-import plyer.platforms.darwin.notification \
  "${ROOT}/main.py"

echo ""
echo "Built: dist/AmpliFi Teleport for Desktop.app"
echo "Next: ./build_macos_dmg.sh --skip-app-build   # creates Setup .dmg with WireGuard auto-install"
