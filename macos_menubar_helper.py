#!/usr/bin/env python3
"""
Standalone macOS menu bar helper for AmpliFi Teleport.

Runs in its own process (own NSApplication) so Qt/PySide6 cannot steal or
destroy the status item. Prints commands to stdout:

  OPEN  — user chose Open Controls
  QUIT  — user chose Quit

Optional argv[1] / AMPLIFI_TRAY_ICON: path to the app icon (PNG/ICNS).
"""

from __future__ import annotations

import os
import sys

from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSImage,
    NSMenu,
    NSMenuItem,
    NSSquareStatusItemLength,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSObject
from PyObjCTools import AppHelper

_RETAINED: list[object] = []


class HelperDelegate(NSObject):
    def openControls_(self, _sender):  # noqa: N802
        print("OPEN", flush=True)

    def quitApp_(self, _sender):  # noqa: N802
        print("QUIT", flush=True)
        AppHelper.stopEventLoop()


def _icon_path() -> str | None:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        candidate = sys.argv[1].strip()
        if os.path.exists(candidate):
            return candidate
    env = os.environ.get("AMPLIFI_TRAY_ICON", "").strip()
    if env and os.path.exists(env):
        return env
    # Same-directory fallback when launched next to the icon
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("tray-icon.png", "tray-icon.icns", "tray-icon.ico"):
        path = os.path.join(here, name)
        if os.path.exists(path):
            return path
    return None


def _load_menu_bar_image(path: str) -> object | None:
    image = NSImage.alloc().initWithContentsOfFile_(path)
    if image is None:
        print(f"ERROR icon_load_failed {path}", flush=True)
        return None
    # Menu bar extras are ~18pt; keep full-color app artwork (not a template).
    image.setSize_((18.0, 18.0))
    image.setTemplate_(False)
    _RETAINED.append(image)
    return image


def main() -> int:
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    delegate = HelperDelegate.alloc().init()
    _RETAINED.append(delegate)

    icon_path = _icon_path()
    image = _load_menu_bar_image(icon_path) if icon_path else None

    length = (
        float(NSSquareStatusItemLength)
        if image is not None
        else float(NSVariableStatusItemLength)
    )
    status = NSStatusBar.systemStatusBar().statusItemWithLength_(length)
    _RETAINED.append(status)

    button = status.button()
    if button is None:
        print("ERROR no_button", flush=True)
        return 1

    button.setToolTip_("AmpliFi Teleport for Desktop")
    if image is not None:
        button.setImage_(image)
        button.setTitle_("")
        print(f"ICON {icon_path}", flush=True)
    else:
        # Last-resort visible glyph if the asset is missing
        button.setTitle_("AT")
        print("WARN no_icon_using_title", flush=True)

    menu = NSMenu.alloc().init()
    open_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Open Controls", "openControls:", ""
    )
    open_item.setTarget_(delegate)
    menu.addItem_(open_item)
    menu.addItem_(NSMenuItem.separatorItem())
    quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Quit", "quitApp:", ""
    )
    quit_item.setTarget_(delegate)
    menu.addItem_(quit_item)
    _RETAINED.append(menu)
    status.setMenu_(menu)

    print("READY", flush=True)
    AppHelper.runEventLoop()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR {exc}", flush=True)
        raise
