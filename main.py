# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)

import logging
import os
import sys
import threading

from PIL import Image
from logging.handlers import RotatingFileHandler

from config import ICON_PATH_PNG
from platform_utils import (
    IS_MACOS,
    ensure_wireguard_available,
    get_log_path,
    run_elevated_startup,
)
from ui import create_control_window, set_tray_icon, show_control_window
from notifications import show_toast

logger = logging.getLogger("AmpliFi Teleport for Desktop")
logger.setLevel(logging.DEBUG)

log_path = get_log_path()
os.makedirs(os.path.dirname(log_path), exist_ok=True)

file_handler = RotatingFileHandler(
    log_path,
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
)
logger.addHandler(file_handler)


def main():
    # Windows: elevate at startup for tunnel service control (UAC).
    # macOS: app stays user-level; tunnel commands prompt via native admin dialog.
    run_elevated_startup()

    icon_holder = {"icon": None}
    exiting = {"done": False}

    def stop_app(*_args):
        if exiting["done"]:
            return
        exiting["done"] = True
        tray = icon_holder.get("icon")
        try:
            if tray is not None:
                tray.stop()
        except Exception:
            pass
        try:
            root.after(0, root.destroy)
        except Exception:
            try:
                root.destroy()
            except Exception:
                pass
        threading.Timer(0.4, lambda: os._exit(0)).start()

    # Create Tk first on every platform
    root = create_control_window(icon=None, quit_callback=stop_app)
    root.update_idletasks()
    show_control_window(icon=None)

    ok, msg = ensure_wireguard_available()
    if not ok:
        logger.error(msg)
        root.after(
            300,
            lambda m=msg: show_toast("WireGuard Required", m.replace("\n", " ")),
        )

    if IS_MACOS:
        _setup_macos_dock(root, stop_app)
    else:
        _setup_windows_tray(root, icon_holder, stop_app)

    logger.info("Application started on %s", sys.platform)

    try:
        root.mainloop()
    finally:
        tray = icon_holder.get("icon")
        if tray is not None:
            try:
                tray.stop()
            except Exception:
                pass


def _setup_macos_dock(root, stop_app):
    """
    macOS: do not use pystray.

    pystray + Tk/CustomTkinter on macOS commonly crashes with SIGTRAP
    ('zsh: trace trap') because both want to own NSApplication / the main thread.

    Closing the window hides it; clicking the Dock icon brings it back.
    Use Quit in the control window (or Cmd+Q) to fully exit.
    """

    def reopen(*_args):
        show_control_window(icon=None)

    try:
        root.createcommand("tk::mac::ReopenApplication", reopen)
    except Exception:
        logger.debug("Could not register macOS Dock reopen handler", exc_info=True)

    try:
        root.createcommand("tk::mac::Quit", stop_app)
    except Exception:
        logger.debug("Could not register macOS Quit handler", exc_info=True)


def _setup_windows_tray(root, icon_holder, stop_app):
    """Windows: system tray via pystray (safe alongside Tk on Win32)."""
    import pystray

    image = Image.open(ICON_PATH_PNG)

    def request_show(icon=None, item=None):
        try:
            root.after(0, lambda: show_control_window(icon_holder.get("icon")))
        except Exception:
            show_control_window(icon_holder.get("icon"))

    def on_quit_from_tray(icon=None, item=None):
        try:
            root.after(0, stop_app)
        except Exception:
            stop_app()

    menu = pystray.Menu(
        pystray.MenuItem("Open Controls", request_show, default=True),
        pystray.MenuItem("Quit", on_quit_from_tray),
    )

    icon = pystray.Icon(
        "AmpliFi Teleport",
        image,
        "AmpliFi Teleport for Desktop",
        menu=menu,
    )
    icon_holder["icon"] = icon
    set_tray_icon(icon)

    tray_thread = threading.Thread(target=icon.run, name="pystray", daemon=True)
    tray_thread.start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
