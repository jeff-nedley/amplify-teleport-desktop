#!/usr/bin/env bash
# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)
#
# Run the unit / mocked functional test suite.
# Safe for headless environments (forces Qt offscreen).
#
# Usage:
#   ./run_tests.sh
#   ./run_tests.sh -v

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# Prefer the active venv's interpreter when present.
if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
    PYTHON="${VIRTUAL_ENV}/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON="python"
else
    echo "[run_tests] ERROR: python3/python not found on PATH" >&2
    exit 1
fi

export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"

echo "[run_tests] Using ${PYTHON} (QT_QPA_PLATFORM=${QT_QPA_PLATFORM})"
"${PYTHON}" -m unittest \
    test_platform \
    test_installer_parity \
    test_tunnel_functional \
    test_ui_functional \
    "$@"
