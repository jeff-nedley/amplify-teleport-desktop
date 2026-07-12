# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)
#
# Build a full Windows release:
#   1. Sync version.iss from VERSION
#   2. PyInstaller one-file .exe
#   3. Compile the Inno Setup installer (unless -SkipInstaller)
#
# Prerequisites:
#   - Python venv with requirements.txt (incl. pyinstaller)
#   - Inno Setup 6 (+ Inno Download Plugin for WireGuard MSI fetch)
#
# Usage:
#   .\build_exe.ps1
#   .\build_exe.ps1 -SkipInstaller
#   .\build_exe.ps1 -SkipClean

param(
    [switch]$SkipInstaller,
    [switch]$SkipClean
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Get-AppVersion {
    $version = (Get-Content -Path (Join-Path $Root "VERSION") -Raw).Trim()
    if (-not $version) {
        throw "VERSION file is empty"
    }
    return $version
}

function Sync-VersionIss([string]$Version) {
    @(
        "; Generated from VERSION — do not edit by hand."
        "#define MyAppVersion `"$Version`""
    ) | Set-Content -Path (Join-Path $Root "version.iss") -Encoding ascii
    Write-Host "Synced version.iss -> $Version"
}

function Find-ISCC {
    $candidates = @(
        "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path $path)) {
            return $path
        }
    }
    $fromPath = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($fromPath) {
        return $fromPath.Source
    }
    return $null
}

$version = Get-AppVersion
Write-Step "AmpliFi Teleport Windows release ($version)"
Sync-VersionIss $version

if (-not $SkipClean) {
    Write-Step "Cleaning previous build/dist output"
    Remove-Item -Recurse -Force build, dist, __pycache__ -ErrorAction SilentlyContinue
}

Write-Step "Building application with PyInstaller"
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
  main.py

$exePath = Join-Path $Root "dist\AmpliFi Teleport for Desktop.exe"
if (-not (Test-Path $exePath)) {
    throw "PyInstaller did not produce: $exePath"
}
Write-Host "Built: $exePath"

if ($SkipInstaller) {
    Write-Host ""
    Write-Host "Skipped Inno Setup (-SkipInstaller). Compile app_installer_script.iss manually when ready."
    exit 0
}

Write-Step "Compiling Inno Setup installer"
$iscc = Find-ISCC
if (-not $iscc) {
    throw @"
Inno Setup compiler (ISCC.exe) not found.
Install Inno Setup 6 and the Inno Download Plugin, then re-run.
Expected locations include:
  ${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe
"@
}

& $iscc (Join-Path $Root "app_installer_script.iss")
if ($LASTEXITCODE -ne 0) {
    throw "ISCC failed with exit code $LASTEXITCODE"
}

$setupPath = Join-Path $Root "dist\Amplifi Teleport For Desktop Setup-$version.exe"
if (-not (Test-Path $setupPath)) {
    throw "Inno Setup did not produce: $setupPath"
}

Write-Host ""
Write-Host "Windows release ready:" -ForegroundColor Green
Write-Host "  $setupPath"
