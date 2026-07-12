#!/usr/bin/env bash
# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)
#
# Build release installers for AmpliFi Teleport for Desktop.
#
# Native packaging still requires the matching OS:
#   macOS   -> Setup .dmg  (./build_macos_dmg.sh)
#   Windows -> Setup .exe  (.\build_exe.ps1 via PowerShell)
#
# Usage:
#   ./build_release.sh                 # build for this machine's OS
#   ./build_release.sh --macos         # macOS DMG only
#   ./build_release.sh --windows       # Windows Setup exe only
#   ./build_release.sh --all           # every target this host can build
#   ./build_release.sh --version=1.2.3 # write VERSION first, then build
#
# Optional:
#   --skip-app-build   (macOS) reuse existing dist/*.app
#   --skip-installer   (Windows) PyInstaller exe only, skip Inno Setup

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

TARGET="auto"
SKIP_APP_BUILD=0
SKIP_INSTALLER=0
SET_VERSION=""

usage() {
    sed -n '2,25p' "$0" | sed 's/^# \?//'
    exit 2
}

for arg in "$@"; do
    case "$arg" in
        --macos) TARGET="macos" ;;
        --windows) TARGET="windows" ;;
        --all) TARGET="all" ;;
        --skip-app-build) SKIP_APP_BUILD=1 ;;
        --skip-installer) SKIP_INSTALLER=1 ;;
        --version=*) SET_VERSION="${arg#*=}" ;;
        -h|--help) usage ;;
        *)
            echo "Unknown argument: $arg" >&2
            usage
            ;;
    esac
done

log() { echo "[build_release] $*"; }
die() { log "ERROR: $*"; exit 1; }

host_os() {
    case "$(uname -s)" in
        Darwin) echo "macos" ;;
        MINGW*|MSYS*|CYGWIN*|Windows_NT) echo "windows" ;;
        *)
            if [[ -n "${OS:-}" && "${OS}" == "Windows_NT" ]]; then
                echo "windows"
            else
                echo "other"
            fi
            ;;
    esac
}

read_version() {
    tr -d '[:space:]' < "${ROOT}/VERSION"
}

write_version() {
    local version="$1"
    [[ -n "$version" ]] || die "VERSION value is empty"
    printf '%s\n' "$version" > "${ROOT}/VERSION"
    cat > "${ROOT}/version.iss" <<EOF
; Generated from VERSION — do not edit by hand.
#define MyAppVersion "${version}"
EOF
    log "Updated VERSION -> ${version}"
}

ensure_python_deps_hint() {
    if ! command -v pyinstaller >/dev/null 2>&1 && ! python3 -c "import PyInstaller" >/dev/null 2>&1; then
        log "WARNING: PyInstaller not found on PATH. Activate your venv first:"
        log "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    fi
}

build_macos() {
    local args=()
    [[ "$SKIP_APP_BUILD" -eq 1 ]] && args+=(--skip-app-build)
    log "Building macOS Setup DMG..."
    bash "${ROOT}/build_macos_dmg.sh" "${args[@]}"
}

find_powershell() {
    if command -v pwsh >/dev/null 2>&1; then
        echo "pwsh"
        return 0
    fi
    if command -v powershell.exe >/dev/null 2>&1; then
        echo "powershell.exe"
        return 0
    fi
    if command -v powershell >/dev/null 2>&1; then
        echo "powershell"
        return 0
    fi
    return 1
}

build_windows() {
    local ps
    if ! ps="$(find_powershell)"; then
        die "PowerShell not found. Run .\\build_exe.ps1 on a Windows machine."
    fi

    local args=()
    [[ "$SKIP_INSTALLER" -eq 1 ]] && args+=(-SkipInstaller)

    log "Building Windows Setup exe via ${ps}..."
    # -File keeps parameter binding correct for build_exe.ps1 switches.
    "$ps" -NoProfile -ExecutionPolicy Bypass -File "${ROOT}/build_exe.ps1" "${args[@]}"
}

HOST="$(host_os)"
BUILT=()
SKIPPED=()

if [[ -n "$SET_VERSION" ]]; then
    write_version "$SET_VERSION"
fi

VERSION="$(read_version)"
[[ -n "$VERSION" ]] || die "VERSION file is empty"

if [[ "$TARGET" == "auto" ]]; then
    case "$HOST" in
        macos|windows) TARGET="$HOST" ;;
        *) die "Unsupported host OS ($(uname -s)). Use --macos or --windows on the matching machine." ;;
    esac
fi

log "Release version: ${VERSION}"
log "Host: ${HOST}  Target: ${TARGET}"
ensure_python_deps_hint

should_build_macos=0
should_build_windows=0
case "$TARGET" in
    macos) should_build_macos=1 ;;
    windows) should_build_windows=1 ;;
    all)
        should_build_macos=1
        should_build_windows=1
        ;;
    *) die "Internal error: unknown target ${TARGET}" ;;
esac

if [[ "$should_build_macos" -eq 1 ]]; then
    if [[ "$HOST" == "macos" ]]; then
        build_macos
        BUILT+=("macOS DMG: dist/Amplifi Teleport For Desktop Setup-${VERSION}.dmg")
    else
        if [[ "$TARGET" == "macos" ]]; then
            die "macOS packaging requires Darwin (pkgbuild/productbuild/hdiutil)."
        fi
        SKIPPED+=("macOS DMG (run ./build_release.sh --macos on a Mac)")
    fi
fi

if [[ "$should_build_windows" -eq 1 ]]; then
    if [[ "$HOST" == "windows" ]]; then
        build_windows
        BUILT+=("Windows Setup: dist/Amplifi Teleport For Desktop Setup-${VERSION}.exe")
    else
        if [[ "$TARGET" == "windows" ]]; then
            die "Windows packaging requires Windows + PowerShell + Inno Setup 6."
        fi
        SKIPPED+=("Windows Setup (run .\\build_release.ps1 on Windows)")
    fi
fi

echo ""
log "Release summary (v${VERSION})"
if [[ ${#BUILT[@]} -gt 0 ]]; then
    for item in "${BUILT[@]}"; do
        log "  built   - ${item}"
    done
else
    die "Nothing was built."
fi
if [[ ${#SKIPPED[@]} -gt 0 ]]; then
    for item in "${SKIPPED[@]}"; do
        log "  skipped - ${item}"
    done
    log "A full dual-OS GitHub release needs one pass on each OS (or CI runners)."
fi
