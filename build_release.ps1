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
#   .\build_release.ps1 -SkipTests

param(
    [switch]$Windows,
    [switch]$MacOS,
    [switch]$All,
    [switch]$SkipInstaller,
    [switch]$SkipAppBuild,
    [switch]$SkipTests,
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Write-Step([string]$Message) {
    Write-Host "[build_release] $Message"
}

function Find-ProjectPython {
    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    foreach ($candidate in @("python", "python3")) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) {
            return $cmd.Source
        }
    }
    return $null
}

function Find-GitBash {
    # Prefer real Git Bash. Ignore WSL's System32\bash.exe — it is not usable for
    # packaging when WSL/Hyper-V is unavailable, and Get-Command finds it first.
    $candidates = @(
        "C:\Program Files\Git\bin\bash.exe",
        "C:\Program Files\Git\usr\bin\bash.exe",
        "${env:LOCALAPPDATA}\Programs\Git\bin\bash.exe",
        "${env:ProgramFiles}\Git\bin\bash.exe"
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path $path)) {
            return $path
        }
    }

    $cmd = Get-Command bash -ErrorAction SilentlyContinue
    if (-not $cmd) {
        return $null
    }
    $source = $cmd.Source
    if ($source -match '(?i)\\(System32|SysWOW64|WindowsApps)\\bash\.exe$') {
        return $null
    }
    return $source
}

function Invoke-UnitTests {
    Write-Step "Running unit tests before packaging..."
    $env:QT_QPA_PLATFORM = if ($env:QT_QPA_PLATFORM) { $env:QT_QPA_PLATFORM } else { "offscreen" }

    $python = Find-ProjectPython
    if (-not $python) {
        throw "python not found. Create/activate .venv first: python -m venv .venv && .\.venv\Scripts\Activate.ps1 && pip install -r requirements.txt"
    }

    & $python -m unittest test_platform test_installer_parity test_tunnel_functional test_ui_functional -v
    if ($LASTEXITCODE -ne 0) {
        throw "Unit tests failed (exit code $LASTEXITCODE). Fix tests before packaging."
    }
}

function Invoke-WindowsBuild {
    $exeArgs = @("-SkipTests")
    if ($SkipInstaller) { $exeArgs += "-SkipInstaller" }
    Write-Step "Invoking build_exe.ps1"
    & (Join-Path $Root "build_exe.ps1") @exeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "build_exe.ps1 failed with exit code $LASTEXITCODE"
    }
}

if ($Version) {
    $trimmed = $Version.Trim()
    Set-Content -Path (Join-Path $Root "VERSION") -Value $trimmed -Encoding ascii
    @(
        "; Generated from VERSION - do not edit by hand."
        "#define MyAppVersion `"$trimmed`""
    ) | Set-Content -Path (Join-Path $Root "version.iss") -Encoding ascii
    Write-Step "Updated VERSION -> $trimmed"
}

# Default target on Windows is a Windows Setup build.
$wantWindows = $Windows -or $All -or (-not $MacOS)
$wantMacOS = $MacOS -or $All

if ($wantMacOS -and -not $wantWindows) {
    $bash = Find-GitBash
    if (-not $bash) {
        throw "macOS packaging requires a Mac (or Git Bash + ./build_release.sh --macos on Darwin)."
    }
    $releaseArgs = @("--macos")
    if ($SkipAppBuild) { $releaseArgs += "--skip-app-build" }
    if ($SkipTests) { $releaseArgs += "--skip-tests" }
    Write-Step "Delegating to build_release.sh via Git Bash"
    & $bash (Join-Path $Root "build_release.sh") @releaseArgs
    if ($LASTEXITCODE -ne 0) {
        throw "build_release.sh failed with exit code $LASTEXITCODE"
    }
    exit 0
}

# Windows builds: run PowerShell packaging directly. Avoid WSL bash and avoid
# an unnecessary bash -> powershell round-trip when Git Bash is present.
if (-not $SkipTests) {
    Invoke-UnitTests
}

if ($wantMacOS) {
    Write-Step "skipped - macOS DMG (run ./build_release.sh --macos on a Mac)"
}

if ($wantWindows) {
    Invoke-WindowsBuild
}
