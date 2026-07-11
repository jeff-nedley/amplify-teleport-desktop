# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)

"""Cross-platform helpers for Windows and macOS native behavior."""

from __future__ import annotations

import json
import logging
import os
import platform
import shlex
import shutil
import subprocess
import sys

logger = logging.getLogger("AmpliFi Teleport for Desktop")

SYSTEM = platform.system()
IS_WINDOWS = SYSTEM == "Windows"
IS_MACOS = SYSTEM == "Darwin"
IS_LINUX = SYSTEM == "Linux"

# AmpliFi router control-panel device icon / platform label
DEVICE_PLATFORM = "Windows" if IS_WINDOWS else ("macOS" if IS_MACOS else "Linux")


def get_config_dir() -> str:
    """Return the per-user application data directory for this OS."""
    if IS_WINDOWS:
        base = os.getenv("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "AmpliFiTeleport")
    if IS_MACOS:
        return os.path.expanduser("~/Library/Application Support/AmpliFiTeleport")
    return os.path.expanduser("~/.config/AmpliFiTeleport")


def get_log_path() -> str:
    return os.path.join(get_config_dir(), "amplifi_teleport.log")


def resource_path(*parts: str) -> str:
    """Resolve a data file path for both frozen and source runs."""
    if getattr(sys, "frozen", False):
        base_path = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, *parts)


def get_icon_path(prefer_png: bool = False) -> str:
    """
    Return the best available tray/window icon for the current platform.
    Windows prefers .ico; macOS (and Linux) prefer .png.
    """
    ico = resource_path("tray-icon.ico")
    png = resource_path("tray-icon.png")

    if IS_WINDOWS and not prefer_png:
        if os.path.exists(ico):
            return ico
        if os.path.exists(png):
            return png
    else:
        if os.path.exists(png):
            return png
        if os.path.exists(ico):
            return ico

    return png if prefer_png else (ico if IS_WINDOWS else png)


def ui_font(size: int, weight: str = "normal") -> tuple:
    """
    Native-feeling UI font using families Tk can actually render.
    (SF Pro is not always available to Tk and can produce a blank UI on macOS.)
    """
    family = _tk_font_family()
    if weight in ("bold", "bold italic"):
        return (family, size, "bold")
    return (family, size)


_CACHED_FONT_FAMILY: str | None = None


def _tk_font_family() -> str:
    """Pick a font family that exists in the current Tk install."""
    global _CACHED_FONT_FAMILY
    if _CACHED_FONT_FAMILY:
        return _CACHED_FONT_FAMILY

    if IS_MACOS:
        candidates = ("Helvetica Neue", "Helvetica", "Lucida Grande", "Arial")
    elif IS_WINDOWS:
        candidates = ("Segoe UI", "Tahoma", "Arial")
    else:
        candidates = ("DejaVu Sans", "Helvetica", "Arial")

    available = set()
    try:
        import tkinter.font as tkfont

        available = set(tkfont.families())
    except Exception:
        logger.debug("Could not query Tk font families", exc_info=True)

    for name in candidates:
        if not available or name in available:
            _CACHED_FONT_FAMILY = name
            return name

    _CACHED_FONT_FAMILY = candidates[0]
    return _CACHED_FONT_FAMILY


def corner_radius(default: int = 12) -> int:
    """Slightly rounder controls on macOS; same overall language elsewhere."""
    if IS_MACOS:
        return max(default, 14)
    return default


def subprocess_kwargs() -> dict:
    """Hide console windows on Windows; no-op elsewhere."""
    if IS_WINDOWS:
        # CREATE_NO_WINDOW = 0x08000000
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}


def which(cmd: str, extra_paths: list[str] | None = None) -> str | None:
    """Find an executable, checking platform-typical install locations first."""
    candidates = list(extra_paths or [])
    if IS_MACOS:
        candidates.extend(
            [
                f"/opt/homebrew/bin/{cmd}",
                f"/usr/local/bin/{cmd}",
                f"/opt/local/bin/{cmd}",
            ]
        )
    elif IS_WINDOWS:
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        candidates.extend(
            [
                os.path.join(program_files, "WireGuard", f"{cmd}.exe"),
                os.path.join(program_files_x86, "WireGuard", f"{cmd}.exe"),
                os.path.join(program_files, "WireGuard", cmd),
            ]
        )

    for path in candidates:
        if path and os.path.isfile(path):
            return path

    return shutil.which(cmd)


def find_wireguard_exe() -> str | None:
    """Windows WireGuard GUI/service controller (wireguard.exe)."""
    return which("wireguard")


def find_wg() -> str | None:
    return which("wg")


def find_wg_quick() -> str | None:
    return which("wg-quick")


def find_bash() -> str | None:
    """Prefer Homebrew bash on macOS (wg-quick needs bash 4+)."""
    if IS_MACOS:
        for path in ("/opt/homebrew/bin/bash", "/usr/local/bin/bash"):
            if os.path.isfile(path):
                return path
    return which("bash") or "/bin/bash"


def is_admin() -> bool:
    if IS_WINDOWS:
        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def run_elevated_startup() -> None:
    """
    Ensure privileges needed for tunnel management.
    Windows: re-launch the whole app elevated (UAC) — required for tunnel services.
    macOS: no-op at startup; tunnel ops elevate per-command (native pattern).
    """
    if not IS_WINDOWS:
        return

    if is_admin():
        return

    import ctypes

    params = subprocess.list2cmdline(sys.argv[1:])
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 1
    )
    sys.exit(0)


def run_privileged(command: list[str], timeout: float | None = 60) -> subprocess.CompletedProcess:
    """
    Run a command with administrator privileges when required.
    Windows: caller is already elevated at startup.
    macOS: prompt via osascript (native admin dialog) when not root.
    """
    kwargs = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        **subprocess_kwargs(),
    }

    if IS_MACOS and not is_admin():
        # Native macOS admin password dialog; keeps the GUI app unprivileged.
        cmd_str = " ".join(shlex.quote(part) for part in command)
        apple_script = f"do shell script {json.dumps(cmd_str)} with administrator privileges"
        return subprocess.run(
            ["osascript", "-e", apple_script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    return subprocess.run(command, **kwargs)


def run_hidden(command: list[str], timeout: float | None = 30, check: bool = False) -> subprocess.CompletedProcess:
    """Run a subprocess without flashing a console window (Windows)."""
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
        **subprocess_kwargs(),
    )


def wireguard_missing_message() -> str:
    if IS_MACOS:
        return (
            "WireGuard tools not found. Install with Homebrew:\n"
            "  brew install wireguard-tools bash\n"
            "Or install the WireGuard app from https://www.wireguard.com/install/"
        )
    if IS_WINDOWS:
        return (
            "WireGuard not found. Install the official Windows client from "
            "https://www.wireguard.com/install/"
        )
    return "WireGuard (wg / wg-quick) not found in PATH."


def ensure_wireguard_available() -> tuple[bool, str]:
    """Verify the platform-appropriate WireGuard tooling is present."""
    if IS_WINDOWS:
        exe = find_wireguard_exe()
        wg = find_wg()
        if not exe:
            return False, wireguard_missing_message()
        if not wg:
            # wg.exe usually ships next to wireguard.exe
            return False, wireguard_missing_message()
        return True, exe

    wg = find_wg()
    wg_quick = find_wg_quick()
    if not wg or not wg_quick:
        return False, wireguard_missing_message()
    return True, wg_quick
