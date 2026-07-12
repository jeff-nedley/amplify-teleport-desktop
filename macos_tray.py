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
import signal
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


def _helper_pids() -> list[int]:
    """PIDs of running AmpliFi menu-bar helper processes."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "macos_menubar_helper.py"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return []
    pids: list[int] = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return pids


def kill_all_menubar_helpers(*, exclude_pid: Optional[int] = None) -> None:
    """Force-remove any leftover menu-bar helpers (orphans from prior quits)."""
    for pid in _helper_pids():
        if exclude_pid is not None and pid == exclude_pid:
            continue
        _force_kill_pid(pid)


def _force_kill_pid(pid: int) -> None:
    if pid <= 0:
        return
    try:
        os.kill(pid, 0)
    except OSError:
        return

    import time

    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            try:
                os.killpg(pid, sig)
            except Exception:
                os.kill(pid, sig)
        except OSError:
            return
        deadline = time.time() + (0.6 if sig == signal.SIGTERM else 0.3)
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except OSError:
                logger.info("Killed menu bar helper pid=%s with %s", pid, sig)
                return
            time.sleep(0.05)
    logger.warning("Menu bar helper pid=%s may still be alive", pid)


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
        self._pid: Optional[int] = None

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def pid(self) -> Optional[int]:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc.pid
        return self._pid

    def start(self) -> bool:
        if self.is_running:
            return True

        script = _helper_script_path()
        if not os.path.exists(script):
            logger.error("Menu bar helper script missing: %s", script)
            return False

        # Clear orphans from previous runs so icons cannot accumulate.
        kill_all_menubar_helpers()

        cmd = [sys.executable, "-u", script]
        env = os.environ.copy()
        env["AMPLIFI_PARENT_PID"] = str(os.getpid())
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
            self._pid = None
            return False

        self._pid = self._proc.pid
        self._thread = threading.Thread(
            target=self._read_loop,
            name="amplifi-menubar-helper",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Started macOS menu bar helper pid=%s icon=%s parent=%s",
            self._proc.pid,
            self._icon_path,
            os.getpid(),
        )
        return True

    def stop(self) -> None:
        """Ask the helper to remove its status item, then ensure the process is gone."""
        self._stopping = True
        proc = self._proc
        pid = self._pid or (proc.pid if proc is not None else None)
        self._proc = None

        if proc is not None and proc.poll() is None and proc.stdin is not None:
            try:
                proc.stdin.write("EXIT\n")
                proc.stdin.flush()
                proc.stdin.close()
            except Exception:
                logger.debug("Could not send EXIT to menu bar helper", exc_info=True)
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass

        if pid is not None:
            _force_kill_pid(pid)
        # Belt-and-suspenders: sweep any helpers still matching the script name.
        kill_all_menubar_helpers()
        self._pid = None

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
