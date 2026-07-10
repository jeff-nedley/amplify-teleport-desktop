# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)

from plyer import notification
import logging
import os

from config import ICON_PATH, ICON_PATH_ICO, ICON_PATH_PNG
from platform_utils import IS_WINDOWS, IS_MACOS

logger = logging.getLogger("AmpliFi Teleport for Desktop")


def show_toast(title, message, icon_path=None):
    """Show a native notification on Windows (toast) and macOS (Notification Center)."""
    try:
        if icon_path is None:
            # plyer on Windows prefers .ico; macOS prefers .png / .icns
            if IS_WINDOWS and os.path.exists(ICON_PATH_ICO):
                icon_path = ICON_PATH_ICO
            elif os.path.exists(ICON_PATH_PNG):
                icon_path = ICON_PATH_PNG
            else:
                icon_path = ICON_PATH

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
