#!/usr/bin/env python3
"""
Standalone macOS menu bar helper for AmpliFi Teleport.

Runs in its own process (own NSApplication) so Qt/PySide6 cannot steal or
destroy the status item. Prints commands to stdout:

  OPEN  — user chose Open Controls
  QUIT  — user chose Quit

Lifetime is paired to the parent app:
  - EXIT on stdin, or stdin EOF
  - AMPLIFI_PARENT_PID disappearing (poll on the Cocoa run loop)
  - SIGTERM / SIGINT

Optional argv[1] / AMPLIFI_TRAY_ICON: path to the app icon (PNG/ICNS).
"""

from __future__ import annotations

import os
import signal
import sys
import threading

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
from Foundation import NSObject, NSTimer
from PyObjCTools import AppHelper

_RETAINED: list[object] = []
_STATUS_ITEM = None
_SHUTTING_DOWN = False
_PARENT_PID = 0


class HelperDelegate(NSObject):
    def openControls_(self, _sender):  # noqa: N802
        print("OPEN", flush=True)

    def quitApp_(self, _sender):  # noqa: N802
        print("QUIT", flush=True)
        _shutdown_status_item()

    def checkParent_(self, _timer):  # noqa: N802
        """Cocoa-main-thread watchdog: exit if the Qt parent is gone."""
        if _SHUTTING_DOWN:
            return
        if _PARENT_PID <= 0:
            return
        try:
            os.kill(_PARENT_PID, 0)
        except OSError:
            print("PARENT_GONE", flush=True)
            _shutdown_status_item()


def _shutdown_status_item() -> None:
    """Remove the menu-bar item, then stop the Cocoa run loop."""
    global _STATUS_ITEM, _SHUTTING_DOWN
    if _SHUTTING_DOWN:
        return
    _SHUTTING_DOWN = True
    status = _STATUS_ITEM
    _STATUS_ITEM = None
    if status is not None:
        try:
            status.setMenu_(None)
        except Exception:
            pass
        try:
            NSStatusBar.systemStatusBar().removeStatusItem_(status)
        except Exception:
            pass
    try:
        AppHelper.stopEventLoop()
    except Exception:
        pass


def _icon_path() -> str | None:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        candidate = sys.argv[1].strip()
        if os.path.exists(candidate):
            return candidate
    env = os.environ.get("AMPLIFI_TRAY_ICON", "").strip()
    if env and os.path.exists(env):
        return env
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
    image.setSize_((18.0, 18.0))
    image.setTemplate_(False)
    _RETAINED.append(image)
    return image


def _watch_parent_stdin() -> None:
    """Exit when the parent sends EXIT or closes stdin."""
    try:
        for raw in sys.stdin:
            if (raw or "").strip().upper() == "EXIT":
                break
    except Exception:
        pass
    AppHelper.callAfter(_shutdown_status_item)


def _install_signal_handlers() -> None:
    def _handler(_signum, _frame):
        AppHelper.callAfter(_shutdown_status_item)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, _handler)
        except Exception:
            pass


def main() -> int:
    global _STATUS_ITEM, _PARENT_PID

    try:
        _PARENT_PID = int(os.environ.get("AMPLIFI_PARENT_PID", "0") or "0")
    except ValueError:
        _PARENT_PID = 0

    _install_signal_handlers()

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
    _STATUS_ITEM = status
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

    watcher = threading.Thread(
        target=_watch_parent_stdin, name="amplifi-menubar-stdin", daemon=True
    )
    watcher.start()

    # Poll parent liveness on the Cocoa main thread (reliable vs background callAfter).
    if _PARENT_PID > 0:
        timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.4, delegate, "checkParent:", None, True
        )
        _RETAINED.append(timer)
        print(f"PARENT {_PARENT_PID}", flush=True)

    print("READY", flush=True)
    AppHelper.runEventLoop()
    _shutdown_status_item()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR {exc}", flush=True)
        raise
