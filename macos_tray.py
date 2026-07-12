"""
macOS helpers for AmpliFi Teleport.

- hide_dock_icon / present_app / activate_app: AppKit bits for the Qt UI process
- MenuBarHelper: spawns macos_menubar_helper.py in a separate process so the
  status item lives in its own NSApplication (Qt cannot destroy it)

Dock / notification identity icons come from the .app bundle when installed
via the DMG. From source, macOS attributes those to Python — no runtime
override is attempted.
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


def _helper_icon_path() -> Optional[str]:
    from platform_utils import resource_path

    for name in ("tray-icon.png", "tray-icon.icns", "tray-icon.ico"):
        path = resource_path(name)
        if os.path.exists(path):
            return path
    return None


class MenuBarHelper:
    """Owns the separate menu-bar helper process."""

    def __init__(
        self,
        *,
        on_open: Callable[[], None],
        on_quit: Callable[[], None],
        icon_path: Optional[str] = None,
    ) -> None:
        self._on_open = on_open
        self._on_quit = on_quit
        self._icon_path = icon_path or _helper_icon_path()
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._stopping = False

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def pid(self) -> Optional[int]:
        proc = self._proc
        return proc.pid if proc is not None and proc.poll() is None else None

    def start(self) -> bool:
        if self.is_running:
            return True

        script = _helper_script_path()
        if not os.path.exists(script):
            logger.error("Menu bar helper script missing: %s", script)
            return False

        cmd = [sys.executable, "-u", script]
        env = os.environ.copy()
        if self._icon_path and os.path.exists(self._icon_path):
            cmd.append(self._icon_path)
            env["AMPLIFI_TRAY_ICON"] = self._icon_path

        try:
            self._stopping = False
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=True,
                env=env,
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
        logger.info(
            "Started macOS menu bar helper pid=%s icon=%s",
            self._proc.pid,
            self._icon_path,
        )
        return True

    def stop(self) -> None:
        """Ask the helper to remove its status item, then ensure the process is gone."""
        import signal

        self._stopping = True
        proc = self._proc
        self._proc = None
        if proc is None:
            return

        pid = proc.pid
        try:
            if proc.poll() is None and proc.stdin is not None:
                try:
                    proc.stdin.write("EXIT\n")
                    proc.stdin.flush()
                    proc.stdin.close()
                except Exception:
                    logger.debug("Could not send EXIT to menu bar helper", exc_info=True)
                try:
                    proc.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    pass

            if proc.poll() is None:
                try:
                    os.killpg(pid, signal.SIGTERM)
                except Exception:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass

            if proc.poll() is None:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    logger.warning("Menu bar helper pid=%s did not exit after SIGKILL", pid)
            else:
                logger.info("Stopped macOS menu bar helper pid=%s", pid)
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
