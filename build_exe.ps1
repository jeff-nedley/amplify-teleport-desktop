# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)

$ErrorActionPreference = "Stop"

# Keep Inno Setup's version.iss aligned with the single VERSION file.
$version = (Get-Content -Path "VERSION" -Raw).Trim()
if (-not $version) {
  throw "VERSION file is empty"
}
@(
  "; Generated from VERSION — do not edit by hand."
  "#define MyAppVersion `"$version`""
) | Set-Content -Path "version.iss" -Encoding ascii

Remove-Item -Recurse -Force build,dist,__pycache__ -ErrorAction SilentlyContinue

pyinstaller --onefile --windowed `
  --name "AmpliFi Teleport for Desktop" `
  --icon tray-icon.ico `
  --add-data "tray-icon.ico;." `
  --add-data "tray-icon.png;." `
  --add-data "VERSION;." `
  --uac-admin `
  --hidden-import config `
  --hidden-import tunnel `
  --hidden-import ui `
  --hidden-import notifications `
  --hidden-import platform_utils `
  --hidden-import teleport `
  --hidden-import PySide6.QtCore `
  --hidden-import PySide6.QtGui `
  --hidden-import PySide6.QtWidgets `
  --collect-all PySide6 `
  --hidden-import plyer.platforms.win.notification `
  main.py
