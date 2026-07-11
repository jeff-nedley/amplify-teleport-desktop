# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)

"""macOS menu bar (status item) integration via AppKit — safe with Tk."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("AmpliFi Teleport for Desktop")

# Strong references so AppKit objects are not garbage-collected
_KEEP_ALIVE = {}


def start_macos_menu_bar(root, icon_path: str, on_open, on_quit):
    """
    Create a menu bar status item on the existing Tk/Cocoa NSApplication.
    Must be called after the Tk root exists (so NSApp is initialized).
    """
    try:
        from AppKit import (
            NSApplication,
            NSApplicationActivationPolicyRegular,
            NSImage,
            NSMenu,
            NSMenuItem,
            NSStatusBar,
            NSVariableStatusItemLength,
        )
        from Foundation import NSObject
    except ImportError as exc:
        raise RuntimeError(
            "pyobjc-framework-Cocoa is required for the macOS menu bar icon. "
            "Install with: pip install 'pyobjc-framework-Cocoa>=10.0'"
        ) from exc

    app = NSApplication.sharedApplication()
    # Keep Regular so the control window can come to the front reliably.
    # (Accessory can prevent Tk windows from activating when run from python.)
    try:
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    except Exception:
        logger.debug("Could not set NSApplication activation policy", exc_info=True)

    class MenuHandler(NSObject):
        def openControls_(self, _sender):
            try:
                root.after(0, on_open)
            except Exception:
                on_open()

        def quitApp_(self, _sender):
            try:
                root.after(0, on_quit)
            except Exception:
                on_quit()

    handler = MenuHandler.alloc().init()

    status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
        NSVariableStatusItemLength
    )
    button = status_item.button()
    if button is not None:
        loaded = False
        if icon_path and os.path.exists(icon_path):
            image = NSImage.alloc().initWithContentsOfFile_(icon_path)
            if image is not None:
                image.setSize_((18.0, 18.0))
                image.setTemplate_(False)
                button.setImage_(image)
                loaded = True
        if not loaded:
            button.setTitle_("AT")
        button.setToolTip_("AmpliFi Teleport for Desktop")

    menu = NSMenu.alloc().init()
    menu.setAutoenablesItems_(False)

    open_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Open Controls", "openControls:", ""
    )
    open_item.setTarget_(handler)
    open_item.setEnabled_(True)
    menu.addItem_(open_item)

    menu.addItem_(NSMenuItem.separatorItem())

    quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Quit", "quitApp:", "q"
    )
    quit_item.setTarget_(handler)
    quit_item.setEnabled_(True)
    menu.addItem_(quit_item)

    status_item.setMenu_(menu)

    _KEEP_ALIVE["handler"] = handler
    _KEEP_ALIVE["status_item"] = status_item
    _KEEP_ALIVE["menu"] = menu
    _KEEP_ALIVE["open_item"] = open_item
    _KEEP_ALIVE["quit_item"] = quit_item
    _KEEP_ALIVE["app"] = app

    logger.info("macOS menu bar status item started")
    return status_item


def stop_macos_menu_bar():
    status_item = _KEEP_ALIVE.pop("status_item", None)
    if status_item is not None:
        try:
            from AppKit import NSStatusBar

            NSStatusBar.systemStatusBar().removeStatusItem_(status_item)
        except Exception:
            logger.debug("Could not remove macOS status item", exc_info=True)
    _KEEP_ALIVE.clear()
