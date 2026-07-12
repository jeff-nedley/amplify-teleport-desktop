#!/usr/bin/env bash
# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)
#
# Build a macOS installer DMG that mirrors the Windows Inno Setup experience:
#   - Wizard-style .pkg (welcome → license → install → conclusion)
#   - Detects WireGuard; if missing, installs it silently during setup
#   - Installs the app to /Applications
#   - Ships an uninstaller that can also remove WireGuard (same prompt as Windows)
#   - Launches the app after install
#
# Prerequisites (on a Mac):
#   - Xcode command-line tools (pkgbuild, productbuild, hdiutil)
#   - Python venv with requirements.txt installed
#   - PyInstaller
#
# Usage:
#   ./build_macos_dmg.sh
#   ./build_macos_dmg.sh --skip-app-build   # reuse existing dist/*.app
#
# Output:
#   dist/Amplifi Teleport For Desktop Setup-<version>.dmg

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

APP_NAME="AmpliFi Teleport for Desktop"
APP_BUNDLE="${APP_NAME}.app"
IDENTIFIER="com.jeffnedley.amplifiteleport"
VERSION="$(tr -d '[:space:]' < "${ROOT}/VERSION")"
SKIP_APP_BUILD=0

for arg in "$@"; do
    case "$arg" in
        --skip-app-build) SKIP_APP_BUILD=1 ;;
        --version=*) VERSION="${arg#*=}" ;;
        *)
            echo "Unknown argument: $arg" >&2
            exit 2
            ;;
    esac
done

if [[ -z "${VERSION}" ]]; then
    echo "ERROR: VERSION is empty (check ${ROOT}/VERSION or --version=)" >&2
    exit 1
fi

# Keep Inno's version.iss aligned when cutting a release from macOS too.
cat > "${ROOT}/version.iss" <<EOF
; Generated from VERSION — do not edit by hand.
#define MyAppVersion "${VERSION}"
EOF

SETUP_BASENAME="Amplifi Teleport For Desktop Setup-${VERSION}"
DIST_DIR="${ROOT}/dist"
BUILD_DIR="${ROOT}/build/macos_installer"
PAYLOAD_DIR="${BUILD_DIR}/payload"
COMPONENT_PKG="${BUILD_DIR}/AmpliFiTeleportComponent.pkg"
PRODUCT_PKG="${DIST_DIR}/${SETUP_BASENAME}.pkg"
DMG_PATH="${DIST_DIR}/${SETUP_BASENAME}.dmg"
DMG_ROOT="${BUILD_DIR}/dmg_root"
SCRIPTS_DIR="${ROOT}/macos/installer/scripts"
RESOURCES_DIR="${ROOT}/macos/installer/resources"
UNINSTALLER_SRC="${ROOT}/macos/uninstaller/Uninstall AmpliFi Teleport.command"
UNINSTALLER_APP_NAME="Uninstall AmpliFi Teleport.app"

log() { echo "[build_macos_dmg] $*"; }

force_rm_rf() {
    # Signed .app bundles often leave non-writable files; chmod then remove.
    # Fall back to sudo if a prior elevated build left root-owned leftovers.
    local target="$1"
    [[ -e "$target" || -L "$target" ]] || return 0
    chmod -R u+w "$target" 2>/dev/null || true
    if rm -rf "$target" 2>/dev/null; then
        return 0
    fi
    log "Retrying cleanup with sudo (permission-denied leftovers): $target"
    sudo chmod -R u+w "$target" 2>/dev/null || true
    sudo rm -rf "$target"
}

require_macos() {
    if [[ "$(uname -s)" != "Darwin" ]]; then
        log "ERROR: This packaging script must run on macOS (needs pkgbuild/productbuild/hdiutil)."
        log "Scripts and installer assets were still validated where possible."
        exit 1
    fi
}

require_tools() {
    local tool
    for tool in pkgbuild productbuild hdiutil ditto; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            log "ERROR: Missing required tool: $tool (install Xcode Command Line Tools)"
            exit 1
        fi
    done
}

build_app() {
    if [[ "$SKIP_APP_BUILD" -eq 1 ]]; then
        log "Skipping app build (--skip-app-build)"
    else
        log "Building .app with PyInstaller..."
        bash "${ROOT}/build_macos.sh"
    fi

    if [[ ! -d "${DIST_DIR}/${APP_BUNDLE}" ]]; then
        log "ERROR: Missing ${DIST_DIR}/${APP_BUNDLE}"
        exit 1
    fi
}

stage_uninstaller_app() {
    # Spotlight / Launchpad index .app bundles, not bare .command scripts.
    local dest="$1"
    local macos_dir="${dest}/Contents/MacOS"
    local resources_dir="${dest}/Contents/Resources"
    local version
    version="$(tr -d '[:space:]' < "${ROOT}/VERSION")"

    rm -rf "$dest"
    mkdir -p "$macos_dir" "$resources_dir"

    cp "$UNINSTALLER_SRC" "${macos_dir}/uninstall"
    chmod 755 "${macos_dir}/uninstall"

    if [[ -f "${ROOT}/tray-icon.png" ]]; then
        # Best-effort icon; Launch Services still indexes the app without it.
        cp "${ROOT}/tray-icon.png" "${resources_dir}/AppIcon.png"
    fi

    cat > "${dest}/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleDisplayName</key>
    <string>Uninstall AmpliFi Teleport</string>
    <key>CFBundleExecutable</key>
    <string>uninstall</string>
    <key>CFBundleIdentifier</key>
    <string>com.jeffnedley.amplifiteleport.uninstall</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Uninstall AmpliFi Teleport</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>${version}</string>
    <key>CFBundleVersion</key>
    <string>${version}</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF
}

stage_payload() {
    log "Staging install payload (Applications)..."
    rm -rf "$PAYLOAD_DIR"
    mkdir -p "${PAYLOAD_DIR}/Applications"

    # App bundle
    ditto "${DIST_DIR}/${APP_BUNDLE}" "${PAYLOAD_DIR}/Applications/${APP_BUNDLE}"

    # Uninstaller as a real .app so Spotlight / Launchpad can find it
    log "Staging ${UNINSTALLER_APP_NAME}"
    stage_uninstaller_app "${PAYLOAD_DIR}/Applications/${UNINSTALLER_APP_NAME}"

    # Privilege helper scripts (installed by postinstall with sudoers)
    mkdir -p "${PAYLOAD_DIR}/Library/Application Support/AmpliFiTeleport/privileged"
    cp "${ROOT}/macos/privileged/wg-helper.sh" \
        "${PAYLOAD_DIR}/Library/Application Support/AmpliFiTeleport/privileged/wg-helper.sh"
    cp "${ROOT}/macos/privileged/install_privileges.sh" \
        "${PAYLOAD_DIR}/Library/Application Support/AmpliFiTeleport/privileged/install_privileges.sh"
    chmod 755 \
        "${PAYLOAD_DIR}/Library/Application Support/AmpliFiTeleport/privileged/wg-helper.sh" \
        "${PAYLOAD_DIR}/Library/Application Support/AmpliFiTeleport/privileged/install_privileges.sh"

    # Keep a script copy under Application Support for recovery / docs
    cp "$UNINSTALLER_SRC" \
        "${PAYLOAD_DIR}/Library/Application Support/AmpliFiTeleport/Uninstall AmpliFi Teleport.command"
    chmod 755 \
        "${PAYLOAD_DIR}/Library/Application Support/AmpliFiTeleport/Uninstall AmpliFi Teleport.command"
}

prepare_scripts() {
    chmod 755 "${SCRIPTS_DIR}/postinstall"
    # Copy helper scripts next to postinstall so the pkg scripts volume has them too
    cp "${ROOT}/macos/privileged/wg-helper.sh" "${SCRIPTS_DIR}/wg-helper.sh"
    cp "${ROOT}/macos/privileged/install_privileges.sh" "${SCRIPTS_DIR}/install_privileges.sh"
    chmod 755 "${SCRIPTS_DIR}/wg-helper.sh" "${SCRIPTS_DIR}/install_privileges.sh"

    if [[ ! -x "${SCRIPTS_DIR}/postinstall" ]]; then
        log "ERROR: postinstall is not executable"
        exit 1
    fi
}

write_distribution() {
    local dist_xml="${BUILD_DIR}/distribution.xml"
    cat > "$dist_xml" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
    <title>AmpliFi Teleport for Desktop</title>
    <organization>com.jeffnedley</organization>
    <domains enable_anywhere="false" enable_currentUserHome="false" enable_localSystem="true"/>
    <options customize="never" require-scripts="true" rootVolumeOnly="true" hostArchitectures="x86_64,arm64"/>
    <welcome file="welcome.html" mime-type="text/html"/>
    <license file="LICENSE" mime-type="text/plain"/>
    <conclusion file="conclusion.html" mime-type="text/html"/>
    <pkg-ref id="${IDENTIFIER}"/>
    <choices-outline>
        <line choice="default"/>
    </choices-outline>
    <choice id="default" title="AmpliFi Teleport for Desktop" description="Desktop client and WireGuard dependency setup">
        <pkg-ref id="${IDENTIFIER}"/>
    </choice>
    <pkg-ref id="${IDENTIFIER}" version="${VERSION}" onConclusion="none">AmpliFiTeleportComponent.pkg</pkg-ref>
</installer-gui-script>
EOF
    echo "$dist_xml"
}

build_packages() {
    log "Building component package..."
    prepare_scripts

    pkgbuild \
        --root "$PAYLOAD_DIR" \
        --scripts "$SCRIPTS_DIR" \
        --identifier "$IDENTIFIER" \
        --version "$VERSION" \
        --install-location "/" \
        "$COMPONENT_PKG"

    local dist_xml
    dist_xml="$(write_distribution)"

    # Copy license into resources for the license pane (same LICENSE as Windows Inno)
    cp "${ROOT}/LICENSE" "${RESOURCES_DIR}/LICENSE"

    log "Building product package (wizard)..."
    mkdir -p "$DIST_DIR"
    productbuild \
        --distribution "$dist_xml" \
        --resources "$RESOURCES_DIR" \
        --package-path "$BUILD_DIR" \
        "$PRODUCT_PKG"

    log "Product package: $PRODUCT_PKG"
}

build_dmg() {
    log "Creating DMG..."
    rm -rf "$DMG_ROOT"
    mkdir -p "$DMG_ROOT"

    cp "$PRODUCT_PKG" "${DMG_ROOT}/${SETUP_BASENAME}.pkg"

    # Short instruction file for users who open the DMG
    cat > "${DMG_ROOT}/README.txt" <<EOF
AmpliFi Teleport for Desktop — macOS Setup
==========================================

1. Double-click "${SETUP_BASENAME}.pkg"
2. Follow the installer (administrator password required)
3. If WireGuard is not already installed, setup installs it silently
   (same behavior as the Windows installer)
4. The app launches when installation finishes

To uninstall later:
  Open "Uninstall AmpliFi Teleport" from Applications
  (you will be asked if you also want to remove WireGuard)
EOF

    rm -f "$DMG_PATH"
    hdiutil create \
        -volname "AmpliFi Teleport Setup" \
        -srcfolder "$DMG_ROOT" \
        -ov \
        -format UDZO \
        "$DMG_PATH"

    log "DMG ready: $DMG_PATH"
}

clean_macos_dist() {
    # Remove prior macOS release outputs so dist/ only has this build's artifacts.
    mkdir -p "$DIST_DIR"
    log "Cleaning previous macOS artifacts from dist/"
    if [[ "$SKIP_APP_BUILD" -eq 0 ]]; then
        rm -rf "${DIST_DIR}/${APP_BUNDLE}"
    else
        log "Keeping existing ${APP_BUNDLE} (--skip-app-build)"
    fi
    # Shell-nullglob equivalent: ignore "no matches" without aborting under set -u
    local path
    shopt -s nullglob
    for path in \
        "${DIST_DIR}/Amplifi Teleport For Desktop Setup-"*.dmg \
        "${DIST_DIR}/Amplifi Teleport For Desktop Setup-"*.pkg
    do
        log "Removing $(basename "$path")"
        rm -f "$path"
    done
    shopt -u nullglob
}

# --- main ---
require_macos
require_tools
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

clean_macos_dist
build_app
stage_payload
build_packages
build_dmg

log "Done."
log "Distribute: $DMG_PATH"
log "Inside the DMG, users run: ${SETUP_BASENAME}.pkg"
