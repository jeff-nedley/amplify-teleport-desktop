# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)

import os

from platform_utils import get_config_dir, get_icon_path, resource_path

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Config paths (APPDATA on Windows, Application Support on macOS)
CONFIG_DIR = get_config_dir()
os.makedirs(CONFIG_DIR, exist_ok=True)

UUID_FILE = os.path.join(CONFIG_DIR, "teleport_uuid")
TOKEN_FILE = os.path.join(CONFIG_DIR, "teleport_token_0")
CONFIG_PATH = os.path.join(CONFIG_DIR, "teleport.conf")

# Tunnel interface / service name (derived from config filename)
TUNNEL_NAME = "teleport"

# Icons: .ico preferred on Windows, .png on macOS (both ship in the repo)
ICON_PATH = get_icon_path(prefer_png=False)
ICON_PATH_PNG = get_icon_path(prefer_png=True)
ICON_PATH_ICO = resource_path("tray-icon.ico")
