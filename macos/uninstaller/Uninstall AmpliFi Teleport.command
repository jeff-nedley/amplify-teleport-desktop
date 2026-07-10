#!/bin/bash
# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)
#
# Uninstall AmpliFi Teleport for Desktop (macOS).
# Mirrors CurUninstallStepChanged in app_installer_script.iss:
#   - Removes the application
#   - If WireGuard is installed, asks whether to uninstall it too

set -euo pipefail

APP_NAME="AmpliFi Teleport for Desktop"
APP_PATH="/Applications/${APP_NAME}.app"
SUPPORT_USER="${HOME}/Library/Application Support/AmpliFiTeleport"
SUPPORT_SYSTEM="/Library/Application Support/AmpliFiTeleport"
LOG_DIR="/Library/Logs/AmpliFiTeleport"
UNINSTALLER_PATH="/Applications/Uninstall AmpliFi Teleport.command"

osascript_dialog() {
    local message="$1"
    local buttons="$2"
    local default_button="$3"
    local icon="${4:-caution}"
    osascript <<EOF
button returned of (display dialog "${message}" with title "Uninstall AmpliFi Teleport" buttons {${buttons}} default button ${default_button} with icon ${icon})
EOF
}

is_wireguard_installed() {
    local wg_path wg_quick_path
    for wg_path in \
        /opt/homebrew/bin/wg \
        /usr/local/bin/wg \
        /opt/local/bin/wg \
        "$(command -v wg 2>/dev/null || true)"
    do
        [[ -z "$wg_path" || ! -x "$wg_path" ]] && continue
        wg_quick_path="$(dirname "$wg_path")/wg-quick"
        if [[ -x "$wg_quick_path" ]]; then
            return 0
        fi
    done
    return 1
}

brew_bin() {
    for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
        if [[ -x "$candidate" ]]; then
            echo "$candidate"
            return 0
        fi
    done
    command -v brew 2>/dev/null || return 1
}

# Confirm uninstall of the app itself
CHOICE="$(osascript_dialog \
    "Do you want to uninstall AmpliFi Teleport for Desktop?" \
    "\"Cancel\", \"Uninstall\"" \
    2 \
    "caution" || true)"

if [[ "$CHOICE" != "Uninstall" ]]; then
    exit 0
fi

# Quit running app if present
osascript -e "tell application \"${APP_NAME}\" to quit" >/dev/null 2>&1 || true
sleep 1
pkill -f "${APP_NAME}" >/dev/null 2>&1 || true

# Remove application bundle
if [[ -d "$APP_PATH" ]]; then
    rm -rf "$APP_PATH"
fi

# Remove user config (tokens / conf / logs) — ask first
CONFIG_CHOICE="$(osascript_dialog \
    "Also delete saved Teleport configuration (PIN token / WireGuard config)?" \
    "\"Keep\", \"Delete\"" \
    1 \
    "note" || true)"

if [[ "$CONFIG_CHOICE" == "Delete" ]]; then
    rm -rf "$SUPPORT_USER"
fi

# Mirror Inno: if WireGuard is installed, ask to remove it
if is_wireguard_installed; then
    WG_CHOICE="$(osascript_dialog \
        "Do you also want to uninstall WireGuard?" \
        "\"No\", \"Yes\"" \
        1 \
        "caution" || true)"

    if [[ "$WG_CHOICE" == "Yes" ]]; then
        if BREW="$(brew_bin)"; then
            # Uninstall only the formulas we may have installed; leave Homebrew itself
            "$BREW" uninstall --quiet wireguard-tools 2>/dev/null || true
            # Do not remove bash — other tools may depend on Homebrew bash
            osascript_dialog \
                "WireGuard tools (wireguard-tools) were removed via Homebrew." \
                "\"OK\"" \
                1 \
                "note" >/dev/null || true
        else
            osascript_dialog \
                "WireGuard tools were detected but Homebrew was not found. Remove them manually if desired." \
                "\"OK\"" \
                1 \
                "stop" >/dev/null || true
        fi
    fi
fi

# Remove system support marker / logs (best effort; may need admin)
rm -rf "$SUPPORT_SYSTEM" 2>/dev/null || true
rm -rf "$LOG_DIR" 2>/dev/null || true

# Remove this uninstaller last
osascript_dialog \
    "AmpliFi Teleport for Desktop has been uninstalled." \
    "\"OK\"" \
    1 \
    "note" >/dev/null || true

rm -f "$UNINSTALLER_PATH" 2>/dev/null || true
exit 0
