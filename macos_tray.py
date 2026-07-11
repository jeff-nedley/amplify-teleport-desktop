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

# Keep strong refs — otherwise the Dock reverts to the Python interpreter icon.
_DOCK_ICON_IMAGE = None
_DOCK_ICON_VIEW = None
_DOCK_ICON_PATH: Optional[str] = None


def hide_dock_icon() -> None:
    """Run as a menu-bar accessory — no Dock icon."""
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    logger.info("macOS activation policy set to Accessory (no Dock icon)")


def _resolve_icon_path(icon_path: Optional[str] = None) -> Optional[str]:
    if icon_path and os.path.exists(icon_path):
        return os.path.abspath(icon_path)

    from platform_utils import resource_path

    for name in ("tray-icon.png", "tray-icon.icns", "tray-icon.ico"):
        candidate = resource_path(name)
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    return None


def set_dock_icon(icon_path: Optional[str] = None) -> bool:
    """
    Set the Dock / app icon to the AmpliFi Teleport artwork.

    Running from source uses the python.org / Homebrew python binary, so macOS
    defaults to the Python Dock icon. Qt also tends to reset the tile after
    show(). We setApplicationIconImage, pin an NSImageView on the Dock tile,
    and keep strong Python refs so the artwork sticks.
    """
    global _DOCK_ICON_IMAGE, _DOCK_ICON_VIEW, _DOCK_ICON_PATH

    from AppKit import NSApplication, NSImage, NSImageView, NSMakeRect
    from Foundation import NSData

    path = _resolve_icon_path(icon_path) or _resolve_icon_path(_DOCK_ICON_PATH)
    if not path:
        logger.warning("No app icon file found for Dock")
        return False

    image = NSImage.alloc().initWithContentsOfFile_(path)
    if image is None:
        try:
            image = NSImage.alloc().initByReferencingFile_(path)
        except Exception:
            image = None
    if image is None:
        data = NSData.dataWithContentsOfFile_(path)
        if data is not None:
            image = NSImage.alloc().initWithData_(data)
    if image is None:
        logger.error("Failed to load Dock icon from %s", path)
        return False

    # Keep full pixel dimensions for a sharp Dock tile (don't shrink to 18pt).
    try:
        reps = image.representations()
        if reps:
            best = max(reps, key=lambda r: int(r.pixelsWide()) * int(r.pixelsHigh()))
            image.setSize_((float(best.pixelsWide()), float(best.pixelsHigh())))
    except Exception:
        try:
            image.setSize_((256.0, 256.0))
        except Exception:
            pass

    _DOCK_ICON_PATH = path
    _DOCK_ICON_IMAGE = image

    app = NSApplication.sharedApplication()
    app.setApplicationIconImage_(image)

    try:
        tile = app.dockTile()
        # Clear any previous custom view, then pin ours.
        try:
            tile.setContentView_(None)
        except Exception:
            pass
        view = NSImageView.alloc().initWithFrame_(NSMakeRect(0, 0, 256, 256))
        try:
            # NSImageScaleProportionallyUpOrDown == 3
            view.setImageScaling_(3)
        except Exception:
            pass
        view.setImage_(image)
        _DOCK_ICON_VIEW = view
        tile.setContentView_(view)
        tile.display()
    except Exception:
        logger.exception("Failed to update Dock tile content view")

    logger.info("Dock / application icon set from %s", path)
    return True


def schedule_dock_icon_refresh(icon_path: Optional[str] = None, *, delays_ms=None) -> None:
    """Re-apply the Dock icon on the Qt event loop (fights Qt resets)."""
    try:
        from PySide6.QtCore import QTimer
    except Exception:
        set_dock_icon(icon_path)
        return

    path = icon_path
    set_dock_icon(path)
    for delay in delays_ms or (0, 50, 100, 250, 500, 1000, 2000):
        QTimer.singleShot(delay, lambda p=path: set_dock_icon(p))



def present_app() -> None:
    """
    Allow a hidden window to come to the front.

    Accessory policy (no Dock) prevents inactive apps from activating their
    windows. Temporarily switch to Regular, then activate.
    """
    from AppKit import NSApplication, NSApplicationActivationPolicyRegular

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    # Policy changes reset the Dock tile to the python.org icon — re-apply ours.
    set_dock_icon()
    app.activateIgnoringOtherApps_(True)
    set_dock_icon()
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
                stdin=subprocess.DEVNULL,
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
