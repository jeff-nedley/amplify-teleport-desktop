#!/bin/bash
# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)
#
# Restricted WireGuard helper for AmpliFi Teleport.
# Intended to be invoked only via:
#   sudo -n /Library/PrivilegedHelperTools/amplifi-teleport-wg-helper ...
#
# Usage:
#   amplifi-teleport-wg-helper up          <absolute-path-to-teleport.conf>
#   amplifi-teleport-wg-helper down        <absolute-path-to-teleport.conf>
#   amplifi-teleport-wg-helper status      <absolute-path-to-teleport.conf>
#   amplifi-teleport-wg-helper restore-dns <absolute-path-to-teleport.conf>
#
# On macOS, wg-quick often leaves DNS pointed at the tunnel resolver after
# "down", so Wi-Fi looks connected but nothing loads. We always restore
# DHCP DNS after teardown.

set -euo pipefail

ACTION="${1:-}"
CONFIG="${2:-}"

usage() {
    echo "Usage: $0 up|down|status|restore-dns /absolute/path/to/teleport.conf" >&2
    exit 2
}

[[ "$ACTION" == "up" || "$ACTION" == "down" || "$ACTION" == "status" || "$ACTION" == "restore-dns" ]] || usage
[[ -n "$CONFIG" && "$CONFIG" == /* ]] || usage

# Only allow teleport.conf under an AmpliFiTeleport application-support folder
if [[ "$(basename "$CONFIG")" != "teleport.conf" || "$CONFIG" != *"/AmpliFiTeleport/teleport.conf" ]]; then
    echo "Refusing config path: $CONFIG" >&2
    exit 3
fi

find_tool() {
    local name="$1"
    for candidate in \
        "/opt/homebrew/bin/${name}" \
        "/usr/local/bin/${name}" \
        "/opt/local/bin/${name}"
    do
        if [[ -x "$candidate" ]]; then
            echo "$candidate"
            return 0
        fi
    done
    command -v "$name" 2>/dev/null || return 1
}

# Reset every network service to DHCP DNS / empty search domains.
# Fixes the common "Wi-Fi connected but no internet" state after wg-quick down.
restore_macos_dns() {
    local service
    if [[ ! -x /usr/sbin/networksetup ]]; then
        return 0
    fi
    /usr/sbin/networksetup -listallnetworkservices 2>/dev/null | /usr/bin/tail -n +2 | while IFS= read -r service; do
        # Disabled services are prefixed with "*"
        service="${service#\*}"
        [[ -z "$service" ]] && continue
        /usr/sbin/networksetup -setdnsservers "$service" Empty >/dev/null 2>&1 || true
        /usr/sbin/networksetup -setsearchdomains "$service" Empty >/dev/null 2>&1 || true
    done
    echo "restored-dns"
}

if [[ "$ACTION" == "restore-dns" ]]; then
    restore_macos_dns
    exit 0
fi

WG_QUICK="$(find_tool wg-quick)" || {
    echo "wg-quick not found" >&2
    exit 4
}

# Prefer Homebrew bash (wg-quick needs bash 4+; system bash is 3.2)
if [[ -x /opt/homebrew/bin/bash ]]; then
    BASH_BIN="/opt/homebrew/bin/bash"
elif [[ -x /usr/local/bin/bash ]]; then
    BASH_BIN="/usr/local/bin/bash"
else
    BASH_BIN="$(find_tool bash || echo /bin/bash)"
fi

if [[ "$ACTION" == "status" ]]; then
    if [[ -e "/var/run/wireguard/teleport.name" || -e "/var/run/wireguard/teleport.sock" ]]; then
        echo "active"
        exit 0
    fi
    echo "inactive"
    exit 1
fi

if [[ "$ACTION" == "up" && ! -f "$CONFIG" ]]; then
    echo "Config not found: $CONFIG" >&2
    exit 5
fi

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

if [[ "$ACTION" == "down" ]]; then
    set +e
    "$BASH_BIN" "$WG_QUICK" down "$CONFIG"
    rc=$?
    set -e
    # Always clear tunnel DNS even if wg-quick reported "not a WireGuard interface"
    restore_macos_dns
    exit "$rc"
fi

# up
exec "$BASH_BIN" "$WG_QUICK" up "$CONFIG"
