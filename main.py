# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)

"""Application entrypoint.

Frozen macOS builds re-exec this same binary for the menu-bar helper. That path
must be selected before importing the Qt UI, or we spawn another full app.
"""

from __future__ import annotations

import logging
import os
import sys


def _is_menubar_helper_mode() -> bool:
    return "--menubar-helper" in sys.argv or os.environ.get("AMPLIFI_MENUBAR_HELPER") == "1"


def _run_menubar_helper() -> int:
    """
    Frozen .app helper entrypoint.

    PyInstaller cannot launch a different .py via sys.executable; re-execing the
    app binary would start another full UI instance (open-loop).
    """
    from macos_menubar_helper import main as menubar_main

    return int(menubar_main() or 0)


def main() -> None:
    from logging.handlers import RotatingFileHandler

    from platform_utils import (
        IS_MACOS,
        ensure_wireguard_available,
        get_log_path,
        macos_helper_ready,
        run_elevated_startup,
    )
    from ui import start_ui

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

    # Windows: elevate at startup for tunnel service control (UAC).
    # macOS: one-time privilege helper install (skipped if DMG already set it up).
    run_elevated_startup()

    app, _window, _tray = start_ui()

    ok, msg = ensure_wireguard_available()
    if not ok:
        logger.error(msg)

    if IS_MACOS and not macos_helper_ready():
        logger.warning(
            "WireGuard helper not ready — approve the administrator prompt on next "
            "connect so Connect/Disconnect do not keep asking for a password"
        )

    logger.info("Application started on %s", sys.platform)
    sys.exit(app.exec())


if __name__ == "__main__":
    if _is_menubar_helper_mode():
        logging.basicConfig(level=logging.INFO)
        raise SystemExit(_run_menubar_helper())

    logging.basicConfig(level=logging.INFO)
    main()
