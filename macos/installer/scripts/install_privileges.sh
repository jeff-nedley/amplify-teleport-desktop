#!/bin/bash
# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)
#
# Install the passwordless WireGuard helper + sudoers rule.
# Must run as root (pkg postinstall, or one-time osascript elevation from the app).
#
# Usage:
#   install_privileges.sh <console-username> [path-to-wg-helper.sh]

set -euo pipefail

USER_NAME="${1:-}"
HELPER_SRC="${2:-}"

HELPER_DST="/Library/PrivilegedHelperTools/amplifi-teleport-wg-helper"
SUDOERS_DST="/etc/sudoers.d/amplifi-teleport"
SUPPORT_DIR="/Library/Application Support/AmpliFiTeleport"

if [[ -z "$USER_NAME" ]]; then
    echo "Usage: $0 <username> [helper-source]" >&2
    exit 2
fi

if [[ "$(id -u)" -ne 0 ]]; then
    echo "This installer must run as root" >&2
    exit 1
fi

# Resolve helper source
if [[ -z "$HELPER_SRC" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    HELPER_SRC="${SCRIPT_DIR}/wg-helper.sh"
fi

if [[ ! -f "$HELPER_SRC" ]]; then
    echo "Helper source not found: $HELPER_SRC" >&2
    exit 1
fi

mkdir -p /Library/PrivilegedHelperTools
mkdir -p "$SUPPORT_DIR"

cp "$HELPER_SRC" "$HELPER_DST"
chown root:wheel "$HELPER_DST"
chmod 755 "$HELPER_DST"

# Passwordless sudo for this user, restricted to the helper binary only
TMP_SUDOERS="$(mktemp)"
cat > "$TMP_SUDOERS" <<EOF
# AmpliFi Teleport for Desktop — passwordless WireGuard helper
# Installed by the app setup; remove with the uninstaller.
${USER_NAME} ALL=(root) NOPASSWD: ${HELPER_DST}
EOF

# Validate before installing (avoids locking the user out of sudo)
if ! visudo -cf "$TMP_SUDOERS" >/dev/null 2>&1; then
    echo "Generated sudoers file failed validation" >&2
    cat "$TMP_SUDOERS" >&2
    rm -f "$TMP_SUDOERS"
    exit 1
fi

cp "$TMP_SUDOERS" "$SUDOERS_DST"
rm -f "$TMP_SUDOERS"
chown root:wheel "$SUDOERS_DST"
chmod 440 "$SUDOERS_DST"

echo "Installed helper at ${HELPER_DST}"
echo "Installed sudoers at ${SUDOERS_DST} for user ${USER_NAME}"
