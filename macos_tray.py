"""
Native macOS menu bar (status item) for AmpliFi Teleport.

Uses AppKit NSStatusItem so the icon appears in the top-right menu bar.
Sets NSApplicationActivationPolicyAccessory so the app has no Dock icon.

Important: with Qt (PySide6), the status item must be created after the
Cocoa app/event loop is alive — otherwise statusItem.button() is None and
nothing appears. Callers should start() via QTimer.singleShot.
"""

from __future__ import annotations

import logging
import os
from typing import Callable, List, Optional

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSImage,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSObject

logger = logging.getLogger(__name__)

# Keep strong refs so PyObjC/GC cannot drop the status item or delegate.
_RETAINED: List[object] = []


class _TrayDelegate(NSObject):
    """Receives NSMenu item actions from the status item."""

    callbacks = objc.ivar()

    def initWithCallbacks_(self, callbacks):  # noqa: N802
        self = objc.super(_TrayDelegate, self).init()
        if self is None:
            return None
        self.callbacks = callbacks
        return self

    def openControls_(self, _sender):  # noqa: N802
        callback = (self.callbacks or {}).get("open")
        if callback:
            callback()

    def quitApp_(self, _sender):  # noqa: N802
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
        self._attempts = 0

    @staticmethod
    def hide_dock_icon() -> None:
        """Run as a menu-bar accessory — no Dock icon."""
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        logger.info("macOS activation policy set to Accessory (no Dock icon)")

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> bool:
        """
        Create the menu bar status item.

        Returns True when the item is visible. Safe to call repeatedly until
        it succeeds (used for deferred/retry from Qt's event loop).
        """
        if self._running:
            return True

        self._attempts += 1
        try:
            self.hide_dock_icon()
        except Exception:
            logger.exception("Failed to set accessory activation policy")

        try:
            status_bar = NSStatusBar.systemStatusBar()
            # Variable length + title guarantees a visible glyph even if the
            # image fails to load (Square length + empty image = invisible).
            self._status_item = status_bar.statusItemWithLength_(
                float(NSVariableStatusItemLength)
            )
            _RETAINED.append(self._status_item)

            button = self._status_item.button()
            if button is None:
                logger.warning(
                    "NSStatusItem.button() is None (attempt %s) — will retry",
                    self._attempts,
                )
                try:
                    status_bar.removeStatusItem_(self._status_item)
                except Exception:
                    pass
                self._status_item = None
                return False

            # Always set a text title so something is visible in the menu bar.
            button.setTitle_("AT")
            button.setToolTip_(self._title)

            icon = self._load_icon()
            if icon is not None:
                button.setImage_(icon)
                # Keep title as well until we know the image is readable;
                # image+title is fine for VariableStatusItemLength.
                try:
                    button.setImagePosition_(1)  # NSImageLeft
                except Exception:
                    pass

            self._delegate = _TrayDelegate.alloc().initWithCallbacks_(
                {"open": self._handle_open, "quit": self._handle_quit}
            )
            _RETAINED.append(self._delegate)

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
            _RETAINED.append(menu)
            self._status_item.setMenu_(menu)
            self._running = True
            logger.info(
                "macOS menu bar status item started (attempt %s, title=AT)",
                self._attempts,
            )
            return True
        except Exception:
            logger.exception(
                "Failed to create macOS status item (attempt %s)", self._attempts
            )
            self._status_item = None
            return False

    def stop(self) -> None:
        if not self._running and self._status_item is None:
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
        if not self._icon_path or not os.path.exists(self._icon_path):
            return None
        try:
            image = NSImage.alloc().initWithContentsOfFile_(self._icon_path)
            if image is None:
                return None
            image.setSize_((18.0, 18.0))
            # Template images adapt to light/dark menu bars.
            image.setTemplate_(True)
            _RETAINED.append(image)
            return image
        except Exception:
            logger.exception("Failed to load menu bar icon from %s", self._icon_path)
            return None
