#!/usr/bin/env python3
"""
Standalone macOS menu bar helper for AmpliFi Teleport.

Runs in its own process (own NSApplication) so Qt/PySide6 cannot steal or
destroy the status item. Prints commands to stdout:

  OPEN  — user chose Open Controls
  QUIT  — user chose Quit

The parent app should terminate this process on exit.
"""

import sys

from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSMenu,
    NSMenuItem,
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


def main() -> int:
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    delegate = HelperDelegate.alloc().init()
    _RETAINED.append(delegate)

    status = NSStatusBar.systemStatusBar().statusItemWithLength_(
        float(NSVariableStatusItemLength)
    )
    _RETAINED.append(status)

    button = status.button()
    if button is None:
        print("ERROR no_button", flush=True)
        return 1

    button.setTitle_("AT")
    button.setToolTip_("AmpliFi Teleport for Desktop")

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
