# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)

import json
import logging
import os
import subprocess

from config import ICON_PATH, ICON_PATH_ICO, ICON_PATH_PNG
from platform_utils import IS_MACOS, IS_WINDOWS

logger = logging.getLogger("AmpliFi Teleport for Desktop")


def show_toast(title, message, icon_path=None):
    """Show a native notification on Windows (toast) and macOS (Notification Center)."""
    try:
        if IS_MACOS:
            _notify_macos(title, message)
            return

        if icon_path is None:
            if IS_WINDOWS and os.path.exists(ICON_PATH_ICO):
                icon_path = ICON_PATH_ICO
            elif os.path.exists(ICON_PATH_PNG):
                icon_path = ICON_PATH_PNG
            else:
                icon_path = ICON_PATH

        from plyer import notification

        kwargs = {
            "title": title,
            "message": message,
            "app_name": "AmpliFi Teleport for Desktop",
            "timeout": 5,
        }
        if icon_path and os.path.exists(icon_path):
            kwargs["app_icon"] = icon_path
        if IS_WINDOWS:
            kwargs["ticker"] = "Notification"

        notification.notify(**kwargs)
    except Exception:
        platform_label = "macOS" if IS_MACOS else ("Windows" if IS_WINDOWS else "desktop")
        logger.error(
            "Error while creating %s notification", platform_label, exc_info=True
        )


def _notify_macos(title, message):
    """
    Native Notification Center via osascript.
    Avoids plyer's pyobjus dependency (often missing in venvs).
    """
    script = (
        "display notification "
        f"{json.dumps(message)} "
        "with title "
        f"{json.dumps(title)} "
        "subtitle "
        f"{json.dumps('AmpliFi Teleport for Desktop')}"
    )
    subprocess.run(
        ["osascript", "-e", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
