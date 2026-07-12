# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)
#
# Windows entry point for release packaging.
# Prefer this on Windows; ./build_release.sh also works from Git Bash.
#
# Usage:
#   .\build_release.ps1
#   .\build_release.ps1 -Windows
#   .\build_release.ps1 -All
#   .\build_release.ps1 -Version 1.2.3
#   .\build_release.ps1 -SkipInstaller

param(
    [switch]$Windows,
    [switch]$MacOS,
    [switch]$All,
    [switch]$SkipInstaller,
    [switch]$SkipAppBuild,
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Write-Step([string]$Message) {
    Write-Host "[build_release] $Message"
}

if ($Version) {
    Set-Content -Path (Join-Path $Root "VERSION") -Value $Version.Trim() -Encoding ascii
    @(
        "; Generated from VERSION — do not edit by hand."
        "#define MyAppVersion `"$($Version.Trim())`""
    ) | Set-Content -Path (Join-Path $Root "version.iss") -Encoding ascii
    Write-Step "Updated VERSION -> $($Version.Trim())"
}

$bash = Get-Command bash -ErrorAction SilentlyContinue
$args = @()
if ($All) { $args += "--all" }
elseif ($MacOS) { $args += "--macos" }
elseif ($Windows -or (-not $MacOS -and -not $All)) { $args += "--windows" }

if ($SkipInstaller) { $args += "--skip-installer" }
if ($SkipAppBuild) { $args += "--skip-app-build" }

if ($bash) {
    & $bash.Source (Join-Path $Root "build_release.sh") @args
    if ($LASTEXITCODE -ne 0) {
        throw "build_release.sh failed with exit code $LASTEXITCODE"
    }
    exit 0
}

# Fallback when Git Bash isn't available: run the Windows builder directly.
if ($MacOS -and -not $Windows -and -not $All) {
    throw "macOS packaging requires a Mac (or Git Bash + ./build_release.sh --macos on Darwin)."
}

if ($All) {
    Write-Step "Git Bash not found; building Windows target only"
    Write-Step "skipped - macOS DMG (run ./build_release.sh --macos on a Mac)"
}

$exeArgs = @()
if ($SkipInstaller) { $exeArgs += "-SkipInstaller" }
Write-Step "Invoking build_exe.ps1 directly"
& (Join-Path $Root "build_exe.ps1") @exeArgs
