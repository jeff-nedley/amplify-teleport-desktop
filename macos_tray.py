"""
macOS helpers for AmpliFi Teleport.

- hide_dock_icon / present_app / activate_app: AppKit bits for the Qt UI process
- MenuBarHelper: spawns macos_menubar_helper.py in a separate process so the
  status item lives in its own NSApplication (Qt cannot destroy it)
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def hide_dock_icon() -> None:
    """Run as a menu-bar accessory — no Dock icon."""
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    logger.info("macOS activation policy set to Accessory (no Dock icon)")


def present_app() -> None:
    """
    Allow a hidden window to come to the front.

    Accessory policy (no Dock) prevents inactive apps from activating their
    windows. Temporarily switch to Regular, then activate.
    """
    from AppKit import NSApplication, NSApplicationActivationPolicyRegular

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    app.activateIgnoringOtherApps_(True)
    logger.info("macOS activation policy set to Regular (presenting window)")


def activate_app() -> None:
    """Bring the app to the foreground without changing activation policy."""
    try:
        from AppKit import NSApplication

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:
        logger.exception("Failed to activate macOS application")


def _helper_script_path() -> str:
    from platform_utils import resource_path

    return resource_path("macos_menubar_helper.py")


class MenuBarHelper:
    """Owns the separate menu-bar helper process."""

    def __init__(
        self,
        *,
        on_open: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_open = on_open
        self._on_quit = on_quit
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._stopping = False

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> bool:
        if self.is_running:
            return True

        script = _helper_script_path()
        if not os.path.exists(script):
            logger.error("Menu bar helper script missing: %s", script)
            return False

        try:
            self._stopping = False
            self._proc = subprocess.Popen(
                [sys.executable, "-u", script],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
        except Exception:
            logger.exception("Failed to launch menu bar helper")
            self._proc = None
            return False

        self._thread = threading.Thread(
            target=self._read_loop,
            name="amplifi-menubar-helper",
            daemon=True,
        )
        self._thread.start()
        logger.info("Started macOS menu bar helper pid=%s", self._proc.pid)
        return True

    def stop(self) -> None:
        self._stopping = True
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception:
            logger.exception("Failed to stop menu bar helper")

    def hide(self) -> None:
        self.stop()

    def _read_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            for raw in proc.stdout:
                line = (raw or "").strip()
                if not line:
                    continue
                logger.info("Menu bar helper: %s", line)
                if line == "OPEN":
                    self._on_open()
                elif line == "QUIT":
                    self._on_quit()
                    break
                elif line.startswith("ERROR"):
                    logger.error("Menu bar helper error: %s", line)
        except Exception:
            if not self._stopping:
                logger.exception("Menu bar helper reader failed")
        finally:
            if not self._stopping and self._proc is proc:
                code = proc.poll()
                logger.warning("Menu bar helper exited (code=%s)", code)
