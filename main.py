# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)

import logging
import os
import sys
import threading

import pystray
from PIL import Image
from logging.handlers import RotatingFileHandler

from config import ICON_PATH_PNG
from platform_utils import (
    ensure_wireguard_available,
    get_log_path,
    run_elevated_startup,
)
from ui import create_control_window, show_control_window
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

    ok, msg = ensure_wireguard_available()
    if not ok:
        logger.error(msg)
        show_toast("WireGuard Required", msg.replace("\n", " "))

    image = Image.open(ICON_PATH_PNG)
    icon_holder = {"icon": None}
    exiting = {"done": False}

    def request_show(icon=None, item=None):
        """Marshal UI show onto the Tk main thread."""
        root = create_control_window(
            icon=icon_holder.get("icon"), quit_callback=on_quit_from_ui
        )
        try:
            root.after(0, lambda: show_control_window(icon_holder.get("icon")))
        except Exception:
            show_control_window(icon_holder.get("icon"))

    def stop_app():
        if exiting["done"]:
            return
        exiting["done"] = True
        tray = icon_holder.get("icon")
        try:
            if tray is not None:
                tray.stop()
        except Exception:
            pass
        root = create_control_window(icon=tray, quit_callback=None)
        try:
            root.after(0, root.destroy)
        except Exception:
            pass
        threading.Timer(0.4, lambda: os._exit(0)).start()

    def on_quit_from_ui():
        stop_app()

    def on_quit_from_tray(icon=None, item=None):
        stop_app()

    # Same menu on both OSes: Open Controls (default left-click on Windows) + Quit
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

    root = create_control_window(icon=icon, quit_callback=on_quit_from_ui)
    show_control_window(icon)

    logger.info("Application started on %s", sys.platform)

    # Tk owns the main thread (required for CustomTkinter on Windows and macOS).
    # Tray / menu-bar icon runs in a daemon thread.
    tray_thread = threading.Thread(target=icon.run, name="pystray", daemon=True)
    tray_thread.start()

    try:
        root.mainloop()
    finally:
        try:
            icon.stop()
        except Exception:
            pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
