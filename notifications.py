# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)

from __future__ import annotations

import json
import logging
import os
import subprocess
import uuid

from config import ICON_PATH, ICON_PATH_ICO, ICON_PATH_PNG
from platform_utils import IS_MACOS, IS_WINDOWS

logger = logging.getLogger("AmpliFi Teleport for Desktop")

# Keep recent macOS notification objects alive so GC cannot drop them pre-delivery.
_MACOS_NOTIFICATION_REFS: list[object] = []


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
    Post from this process (not osascript).

    Notification Center uses the delivering app's bundle icon. From source
    that is Python; from the DMG/.app it is AmpliFi Teleport.
    """
    if _notify_macos_user_notifications(title, message):
        return
    if _notify_macos_nsusernotification(title, message):
        return

    logger.warning("AppKit notification failed; falling back to osascript")
    _notify_macos_osascript(title, message)


def _notify_macos_user_notifications(title, message) -> bool:
    """macOS 10.14+ UserNotifications (identity icon only — no attachment)."""
    try:
        from UserNotifications import (
            UNMutableNotificationContent,
            UNNotificationRequest,
            UNNotificationSound,
            UNUserNotificationCenter,
        )
    except Exception:
        return False

    try:
        center = UNUserNotificationCenter.currentNotificationCenter()
        try:
            # UNAuthorizationOptionBadge|Sound|Alert
            center.requestAuthorizationWithOptions_completionHandler_(
                (1 << 0) | (1 << 1) | (1 << 2),
                lambda _granted, _error: None,
            )
        except Exception:
            pass

        content = UNMutableNotificationContent.alloc().init()
        content.setTitle_(str(title))
        content.setSubtitle_("AmpliFi Teleport for Desktop")
        content.setBody_(str(message))
        try:
            content.setSound_(UNNotificationSound.defaultSound())
        except Exception:
            pass

        request = UNNotificationRequest.requestWithIdentifier_content_trigger_(
            f"amplifi-{uuid.uuid4()}",
            content,
            None,
        )
        _MACOS_NOTIFICATION_REFS[:] = _MACOS_NOTIFICATION_REFS[-8:] + [content, request]

        def _on_add(error):
            if error is not None:
                logger.error("UNUserNotification delivery error: %s", error)

        center.addNotificationRequest_withCompletionHandler_(request, _on_add)
        logger.info("Posted UserNotifications banner (%s)", title)
        return True
    except Exception:
        logger.debug("UserNotifications path failed", exc_info=True)
        return False


def _notify_macos_nsusernotification(title, message) -> bool:
    """Legacy NSUserNotification (identity icon only — no contentImage)."""
    try:
        from Foundation import NSUserNotification, NSUserNotificationCenter
    except Exception:
        return False

    try:
        note = NSUserNotification.alloc().init()
        note.setTitle_(str(title))
        note.setSubtitle_("AmpliFi Teleport for Desktop")
        note.setInformativeText_(str(message))
        try:
            note.setSoundName_("NSUserNotificationDefaultSoundName")
        except Exception:
            pass

        _MACOS_NOTIFICATION_REFS[:] = _MACOS_NOTIFICATION_REFS[-8:] + [note]
        NSUserNotificationCenter.defaultUserNotificationCenter().deliverNotification_(
            note
        )
        logger.info("Posted NSUserNotification banner (%s)", title)
        return True
    except Exception:
        logger.debug("NSUserNotification path failed", exc_info=True)
        return False


def _notify_macos_osascript(title, message):
    """Last-resort fallback — banners are attributed to Script Editor / osascript."""
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
