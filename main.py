# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)

import logging
import os
import sys

from logging.handlers import RotatingFileHandler

from platform_utils import ensure_wireguard_available, get_log_path, run_elevated_startup
from notifications import show_toast
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


def main():
    # Windows: elevate at startup for tunnel service control (UAC).
    # macOS: app stays user-level; tunnel commands prompt via native admin dialog.
    run_elevated_startup()

    app, window, _tray = start_ui()

    ok, msg = ensure_wireguard_available()
    if not ok:
        logger.error(msg)
        show_toast("WireGuard Required", msg.replace("\n", " "))

    logger.info("Application started on %s", sys.platform)
    sys.exit(app.exec())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
