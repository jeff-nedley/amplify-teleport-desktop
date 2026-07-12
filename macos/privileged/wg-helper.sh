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
# IMPORTANT (macOS): Do NOT put DNS= in the WireGuard config for wg-quick.
# wg-quick's background route monitor can call set_dns AFTER del_dns on down,
# leaving Wi-Fi "connected" with a dead tunnel resolver. We apply/clear DNS
# ourselves instead.

set -euo pipefail

ACTION="${1:-}"
CONFIG="${2:-}"

usage() {
    echo "Usage: $0 up|down|status|restore-dns /absolute/path/to/teleport.conf" >&2
    exit 2
}

[[ "$ACTION" == "up" || "$ACTION" == "down" || "$ACTION" == "status" || "$ACTION" == "restore-dns" ]] || usage
[[ -n "$CONFIG" && "$CONFIG" == /* ]] || usage

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

each_network_service() {
    local service
    /usr/sbin/networksetup -listallnetworkservices 2>/dev/null | /usr/bin/tail -n +2 | while IFS= read -r service; do
        service="${service#\*}"
        [[ -z "$service" ]] && continue
        printf '%s\n' "$service"
    done
}

# Reset every network service to DHCP DNS / empty search domains.
restore_macos_dns() {
    local service
    if [[ ! -x /usr/sbin/networksetup ]]; then
        return 0
    fi
    while IFS= read -r service; do
        /usr/sbin/networksetup -setdnsservers "$service" Empty >/dev/null 2>&1 || true
        /usr/sbin/networksetup -setsearchdomains "$service" Empty >/dev/null 2>&1 || true
    done < <(each_network_service)
}

flush_dns_cache() {
    /usr/bin/dscacheutil -flushcache >/dev/null 2>&1 || true
    /usr/bin/killall -HUP mDNSResponder >/dev/null 2>&1 || true
    /usr/bin/killall -HUP mDNSResponderHelper >/dev/null 2>&1 || true
}

# Apply AmpliFi tunnel DNS to all services (used while the tunnel is up).
apply_tunnel_dns() {
    local service dns_line dns_args=()
    [[ -f "$CONFIG" ]] || return 0

    # Prefer explicit sidecar written by the app; fall back to commented marker.
    if [[ -f "${CONFIG}.dns" ]]; then
        # shellcheck disable=SC2207
        dns_args=( $(/bin/cat "${CONFIG}.dns" 2>/dev/null | tr ',;' ' ') )
    else
        dns_line="$(
            /usr/bin/grep -E '^[[:space:]]*#[[:space:]]*AmpliFiTeleportDNS[[:space:]]*=' "$CONFIG" 2>/dev/null \
                | /usr/bin/tail -n 1 \
                | /usr/bin/sed -E 's/^[[:space:]]*#[[:space:]]*AmpliFiTeleportDNS[[:space:]]*=[[:space:]]*//' \
                | /usr/bin/sed -E 's/[[:space:]]+#.*$//'
        )"
        # shellcheck disable=SC2206
        dns_args=( ${dns_line//,/ } )
    fi

    if [[ ${#dns_args[@]} -eq 0 ]]; then
        echo "no-tunnel-dns"
        return 0
    fi

    while IFS= read -r service; do
        /usr/sbin/networksetup -setdnsservers "$service" "${dns_args[@]}" >/dev/null 2>&1 || true
        /usr/sbin/networksetup -setsearchdomains "$service" Empty >/dev/null 2>&1 || true
    done < <(each_network_service)
    echo "applied-dns ${dns_args[*]}"
}

# Beat the wg-quick monitor race: it can re-apply tunnel DNS via ALRM after down.
restore_macos_dns_hardened() {
    local i
    restore_macos_dns
    for i in 1 2 3 4 5; do
        /bin/sleep 1
        restore_macos_dns
    done
    flush_dns_cache
    # One last pass after cache flush
    /bin/sleep 1
    restore_macos_dns
    echo "restored-dns-hardened"
}

if [[ "$ACTION" == "restore-dns" ]]; then
    restore_macos_dns_hardened
    exit 0
fi

WG_QUICK="$(find_tool wg-quick)" || {
    echo "wg-quick not found" >&2
    exit 4
}

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
    # Wait for wireguard-go / route monitor to exit, then clear DNS repeatedly.
    /bin/sleep 1
    restore_macos_dns_hardened
    exit "$rc"
fi

# up — bring interface up without wg-quick DNS management, then set DNS ourselves.
set +e
"$BASH_BIN" "$WG_QUICK" up "$CONFIG"
rc=$?
set -e
if [[ $rc -eq 0 ]]; then
    apply_tunnel_dns
    flush_dns_cache
fi
exit "$rc"
