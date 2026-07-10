#!/usr/bin/env bash
# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)
#
# Build a macOS .app bundle with PyInstaller.
# Prerequisites:
#   brew install wireguard-tools bash
#   python3 -m venv .venv && source .venv/bin/activate
#   pip install -r requirements.txt
#
# Usage:
#   ./build_macos.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

rm -rf build dist __pycache__

# On macOS, --add-data uses colon separators
pyinstaller --noconfirm --windowed --name "AmpliFi Teleport for Desktop" \
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
echo "WireGuard tools must be installed separately: brew install wireguard-tools bash"
