"""
Native macOS menu bar (status item) for AmpliFi Teleport.

Uses AppKit NSStatusItem so the icon appears in the top-right menu bar.
Sets NSApplicationActivationPolicyAccessory so the app has no Dock icon.
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Optional

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBezierPath,
    NSColor,
    NSImage,
    NSMakeRect,
    NSMenu,
    NSMenuItem,
    NSSquareStatusItemLength,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSObject

logger = logging.getLogger(__name__)


class _TrayDelegate(NSObject):
    """Receives NSMenu item actions from the status item."""

    callbacks = None

    def initWithCallbacks_(self, callbacks):
        self = objc.super(_TrayDelegate, self).init()
        if self is None:
            return None
        self.callbacks = callbacks
        return self

    def openControls_(self, _sender):
        callback = (self.callbacks or {}).get("open")
        if callback:
            callback()

    def quitApp_(self, _sender):
        callback = (self.callbacks or {}).get("quit")
        if callback:
            callback()


class MacOSTray:
    """Menu-bar status item with Open Controls / Quit."""

    def __init__(
        self,
        *,
        on_open: Callable[[], None],
        on_quit: Callable[[], None],
        title: str = "AmpliFi Teleport",
        icon_path: Optional[str] = None,
    ) -> None:
        self._on_open = on_open
        self._on_quit = on_quit
        self._title = title
        self._icon_path = icon_path
        self._status_item = None
        self._delegate = None
        self._menu = None
        self._running = False

    @staticmethod
    def hide_dock_icon() -> None:
        """Run as a menu-bar accessory — no Dock icon."""
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        logger.info("macOS activation policy set to Accessory (no Dock icon)")

    def start(self) -> None:
        if self._running:
            return

        self.hide_dock_icon()

        status_bar = NSStatusBar.systemStatusBar()
        try:
            length = NSSquareStatusItemLength
        except Exception:
            length = NSVariableStatusItemLength

        self._status_item = status_bar.statusItemWithLength_(length)
        button = self._status_item.button()
        if button is None:
            logger.error("NSStatusItem has no button — menu bar icon unavailable")
            return

        icon = self._load_icon()
        if icon is not None:
            button.setImage_(icon)
        else:
            button.setTitle_("AT")

        button.setToolTip_(self._title)

        self._delegate = _TrayDelegate.alloc().initWithCallbacks_(
            {"open": self._handle_open, "quit": self._handle_quit}
        )

        menu = NSMenu.alloc().init()
        open_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Open Controls", "openControls:", ""
        )
        open_item.setTarget_(self._delegate)
        menu.addItem_(open_item)

        menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit", "quitApp:", ""
        )
        quit_item.setTarget_(self._delegate)
        menu.addItem_(quit_item)

        self._menu = menu
        self._status_item.setMenu_(menu)
        self._running = True
        logger.info("macOS menu bar status item started")

    def stop(self) -> None:
        if not self._running:
            return
        try:
            if self._status_item is not None:
                NSStatusBar.systemStatusBar().removeStatusItem_(self._status_item)
        except Exception:
            logger.exception("Failed to remove status item")
        self._status_item = None
        self._delegate = None
        self._menu = None
        self._running = False

    def hide(self) -> None:
        """Compatibility with QSystemTrayIcon.hide() used on quit."""
        self.stop()

    def _handle_open(self) -> None:
        try:
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        except Exception:
            pass
        self._on_open()

    def _handle_quit(self) -> None:
        self._on_quit()

    def _load_icon(self) -> Optional[object]:
        if self._icon_path and os.path.exists(self._icon_path):
            try:
                image = NSImage.alloc().initWithContentsOfFile_(self._icon_path)
                if image is not None:
                    image.setSize_((18.0, 18.0))
                    image.setTemplate_(True)
                    return image
            except Exception:
                logger.exception("Failed to load menu bar icon from %s", self._icon_path)
        return self._make_fallback_icon()

    @staticmethod
    def _make_fallback_icon() -> Optional[object]:
        """Draw a simple template (monochrome) glyph for the menu bar."""
        try:
            size = 18.0
            image = NSImage.alloc().initWithSize_((size, size))
            image.lockFocus()

            NSColor.blackColor().set()
            outer = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(1.5, 1.5, size - 3.0, size - 3.0),
                3.0,
                3.0,
            )
            outer.setLineWidth_(1.6)
            outer.stroke()

            path = NSBezierPath.bezierPath()
            path.moveToPoint_((size / 2.0, 4.5))
            path.lineToPoint_((size - 4.5, size / 2.0))
            path.lineToPoint_((size / 2.0, size - 4.5))
            path.lineToPoint_((4.5, size / 2.0))
            path.closePath()
            path.setLineWidth_(1.4)
            path.stroke()

            image.unlockFocus()
            image.setTemplate_(True)
            return image
        except Exception:
            logger.exception("Failed to create menu bar template icon")
            return None
