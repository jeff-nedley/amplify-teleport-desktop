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

# On macOS, --add-data uses colon separators
pyinstaller --noconfirm --windowed --name "AmpliFi Teleport for Desktop" \
  --distpath dist \
  --workpath build/pyinstaller_app \
  --specpath build/pyinstaller_app \
  --icon tray-icon.png \
  --add-data "tray-icon.ico:." \
  --add-data "tray-icon.png:." \
  --hidden-import config \
  --hidden-import tunnel \
  --hidden-import ui \
  --hidden-import notifications \
  --hidden-import platform_utils \
  --hidden-import teleport \
  --hidden-import plyer.platforms.darwin.notification \
  main.py

echo ""
echo "Built: dist/AmpliFi Teleport for Desktop.app"
echo "Next: ./build_macos_dmg.sh --skip-app-build   # creates Setup .dmg with WireGuard auto-install"
