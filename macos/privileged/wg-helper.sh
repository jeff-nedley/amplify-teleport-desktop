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
# DNS handling:
#   - Never put DNS= in the WireGuard config (wg-quick's monitor can race on down).
#   - On up: snapshot each service's DNS, then apply only our tunnel DNS.
#   - On down: restore the snapshot (not a blanket Empty), so custom DNS is kept.

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

DNS_BACKUP="${CONFIG}.dns-backup"
DNS_SIDECAR="${CONFIG}.dns"

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

# Encode a value for the backup file (spaces -> unit separator friendly).
# Format per line: service<TAB>dns|Empty<TAB>search|Empty
# DNS/search lists use commas between entries.
read_service_dns() {
    local service="$1"
    local raw
    raw="$(/usr/sbin/networksetup -getdnsservers "$service" 2>/dev/null || true)"
    if [[ -z "$raw" || "$raw" == *"aren't any DNS Servers"* || "$raw" == *"Error"* ]]; then
        printf 'Empty'
    else
        printf '%s' "$raw" | /usr/bin/tr '\n' ',' | /usr/bin/sed 's/,$//'
    fi
}

read_service_search() {
    local service="$1"
    local raw
    raw="$(/usr/sbin/networksetup -getsearchdomains "$service" 2>/dev/null || true)"
    if [[ -z "$raw" || "$raw" == *"aren't any Search Domains"* || "$raw" == *"Error"* ]]; then
        printf 'Empty'
    else
        printf '%s' "$raw" | /usr/bin/tr '\n' ',' | /usr/bin/sed 's/,$//'
    fi
}

set_service_dns() {
    local service="$1"
    local dns_csv="$2"
    local search_csv="$3"
    local -a dns_args=()
    local -a search_args=()
    if [[ -z "$dns_csv" || "$dns_csv" == "Empty" ]]; then
        /usr/sbin/networksetup -setdnsservers "$service" Empty >/dev/null 2>&1 || true
    else
        IFS=',' read -r -a dns_args <<< "$dns_csv"
        /usr/sbin/networksetup -setdnsservers "$service" "${dns_args[@]}" >/dev/null 2>&1 || true
    fi

    if [[ -z "$search_csv" || "$search_csv" == "Empty" ]]; then
        /usr/sbin/networksetup -setsearchdomains "$service" Empty >/dev/null 2>&1 || true
    else
        IFS=',' read -r -a search_args <<< "$search_csv"
        /usr/sbin/networksetup -setsearchdomains "$service" "${search_args[@]}" >/dev/null 2>&1 || true
    fi
}

snapshot_dns() {
    local service dns_csv search_csv
    : > "$DNS_BACKUP"
    while IFS= read -r service; do
        dns_csv="$(read_service_dns "$service")"
        search_csv="$(read_service_search "$service")"
        printf '%s\t%s\t%s\n' "$service" "$dns_csv" "$search_csv" >> "$DNS_BACKUP"
    done < <(each_network_service)
    echo "snapshotted-dns"
}

restore_dns_from_backup() {
    local service dns_csv search_csv
    if [[ ! -f "$DNS_BACKUP" ]]; then
        echo "no-dns-backup"
        return 1
    fi
    while IFS=$'\t' read -r service dns_csv search_csv; do
        [[ -z "$service" ]] && continue
        set_service_dns "$service" "$dns_csv" "$search_csv"
    done < "$DNS_BACKUP"
    echo "restored-dns-from-backup"
    return 0
}

# Fallback when no snapshot exists: only clear DNS that still matches our tunnel DNS.
clear_only_tunnel_dns() {
    local service current tunnel_csv tunnel_norm current_norm
    local -a tunnel_args=()

    if [[ -f "$DNS_SIDECAR" ]]; then
        # shellcheck disable=SC2207
        tunnel_args=( $(/bin/cat "$DNS_SIDECAR" 2>/dev/null | tr ',;' ' ') )
    fi
    if [[ ${#tunnel_args[@]} -eq 0 ]]; then
        echo "no-tunnel-dns-to-clear"
        return 0
    fi

    tunnel_csv="$(IFS=','; echo "${tunnel_args[*]}")"
    tunnel_norm="$(printf '%s' "$tunnel_csv" | tr ' ' ',' )"

    while IFS= read -r service; do
        current="$(read_service_dns "$service")"
        current_norm="$(printf '%s' "$current" | tr ' ' ',')"
        # Exact match to what we apply on up — leave custom/other DNS alone.
        if [[ "$current_norm" == "$tunnel_norm" ]]; then
            set_service_dns "$service" "Empty" "Empty"
        fi
    done < <(each_network_service)
    echo "cleared-matching-tunnel-dns"
}

flush_dns_cache() {
    /usr/bin/dscacheutil -flushcache >/dev/null 2>&1 || true
    /usr/bin/killall -HUP mDNSResponder >/dev/null 2>&1 || true
    /usr/bin/killall -HUP mDNSResponderHelper >/dev/null 2>&1 || true
}

apply_tunnel_dns() {
    local service
    local -a dns_args=()

    if [[ -f "$DNS_SIDECAR" ]]; then
        # shellcheck disable=SC2207
        dns_args=( $(/bin/cat "$DNS_SIDECAR" 2>/dev/null | tr ',;' ' ') )
    else
        local dns_line
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

# Restore carefully, with retries to beat any lingering wg-quick monitor ALRM.
restore_dns_hardened() {
    local i
    if ! restore_dns_from_backup; then
        clear_only_tunnel_dns
    fi
    for i in 1 2 3 4; do
        /bin/sleep 1
        if [[ -f "$DNS_BACKUP" ]]; then
            restore_dns_from_backup || true
        else
            clear_only_tunnel_dns
        fi
    done
    flush_dns_cache
    /bin/sleep 1
    if [[ -f "$DNS_BACKUP" ]]; then
        restore_dns_from_backup || true
        /bin/rm -f "$DNS_BACKUP"
    else
        clear_only_tunnel_dns
    fi
    echo "restored-dns-hardened"
}

if [[ "$ACTION" == "restore-dns" ]]; then
    restore_dns_hardened
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
    /bin/sleep 1
    restore_dns_hardened
    exit "$rc"
fi

# up: snapshot existing DNS first, then bring tunnel up, then apply ours.
snapshot_dns
set +e
"$BASH_BIN" "$WG_QUICK" up "$CONFIG"
rc=$?
set -e
if [[ $rc -eq 0 ]]; then
    apply_tunnel_dns
    flush_dns_cache
else
    # Failed up — put DNS back immediately and drop the snapshot.
    restore_dns_from_backup || true
    /bin/rm -f "$DNS_BACKUP"
fi
exit "$rc"
