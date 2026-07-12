# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)

import os

from platform_utils import get_config_dir, get_icon_path, resource_path

APP_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_app_version() -> str:
    """Read the release version from the repo/bundle VERSION file."""
    candidates = (
        resource_path("VERSION"),
        os.path.join(APP_DIR, "VERSION"),
    )
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as handle:
                value = handle.read().strip()
            if value:
                return value
        except OSError:
            continue
    return "0.0.0"


APP_VERSION = _load_app_version()

# Config paths (APPDATA on Windows, Application Support on macOS)
CONFIG_DIR = get_config_dir()
os.makedirs(CONFIG_DIR, exist_ok=True)

UUID_FILE = os.path.join(CONFIG_DIR, "teleport_uuid")
TOKEN_FILE = os.path.join(CONFIG_DIR, "teleport_token_0")
CONFIG_PATH = os.path.join(CONFIG_DIR, "teleport.conf")

# Tunnel interface / service name (derived from config filename)
TUNNEL_NAME = "teleport"

# Local marker used on macOS so status checks never need an admin password prompt
TUNNEL_ACTIVE_MARKER = os.path.join(CONFIG_DIR, "tunnel_active")

# Icons: .ico preferred on Windows, .png on macOS (both ship in the repo)
ICON_PATH_PNG = get_icon_path(prefer_png=True)
ICON_PATH_ICO = resource_path("tray-icon.ico")
