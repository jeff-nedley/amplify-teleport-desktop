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


# macOS passwordless WireGuard helper (installed by DMG postinstall or one-time bootstrap)
MACOS_WG_HELPER = "/Library/PrivilegedHelperTools/amplifi-teleport-wg-helper"
MACOS_SUDOERS = "/etc/sudoers.d/amplifi-teleport"


def _macos_helper_source() -> str | None:
    candidates = [
        resource_path("macos", "privileged", "wg-helper.sh"),
        resource_path("wg-helper.sh"),
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "macos",
            "privileged",
            "wg-helper.sh",
        ),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def _macos_install_script() -> str | None:
    candidates = [
        resource_path("macos", "privileged", "install_privileges.sh"),
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "macos",
            "privileged",
            "install_privileges.sh",
        ),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def macos_helper_ready() -> bool:
    """True when passwordless sudo to the WireGuard helper works."""
    if not IS_MACOS:
        return False
    if not os.path.isfile(MACOS_WG_HELPER):
        return False
    try:
        # Use the real per-user config path so the helper's path guard accepts it
        config_path = os.path.expanduser(
            "~/Library/Application Support/AmpliFiTeleport/teleport.conf"
        )
        result = subprocess.run(
            ["sudo", "-n", MACOS_WG_HELPER, "status", config_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        combined = f"{result.stdout or ''}{result.stderr or ''}".lower()
        if "password" in combined or "a password is required" in combined:
            return False
        # 0 = active, 1 = inactive — both mean sudo -n worked
        if result.returncode in (0, 1):
            return True
        if "sudo:" in combined and (
            "not allowed" in combined or "password is required" in combined
        ):
            return False
        # Other helper errors still prove sudo worked
        return "sudo:" not in combined
    except Exception:
        logger.debug("macos_helper_ready check failed", exc_info=True)
        return False


def macos_helper_outdated() -> bool:
    """True when the installed helper differs from the one shipped with the app."""
    if not IS_MACOS:
        return False
    src = _macos_helper_source()
    if not src or not os.path.isfile(MACOS_WG_HELPER):
        return False
    try:
        import hashlib

        def _sha(path: str) -> str:
            digest = hashlib.sha256()
            with open(path, "rb") as handle:
                for chunk in iter(lambda: handle.read(65536), b""):
                    digest.update(chunk)
            return digest.hexdigest()

        return _sha(src) != _sha(MACOS_WG_HELPER)
    except OSError:
        return True


def install_macos_privileges(force: bool = False) -> tuple[bool, str]:
    """
    One-time admin prompt that installs the helper + sudoers rule.
    After this succeeds, Connect/Disconnect never ask for a password again.
    Pass force=True (or when the shipped helper is newer) to refresh the helper.
    """
    if not IS_MACOS:
        return True, "not macOS"

    outdated = macos_helper_outdated()
    if macos_helper_ready() and not force and not outdated:
        return True, "already installed"

    helper_src = _macos_helper_source()
    install_script = _macos_install_script()
    if not helper_src or not install_script:
        return False, (
            "Privilege helper scripts are missing from the app bundle. "
            "Reinstall from the Setup DMG, or run from a full source checkout."
        )

    import getpass

    user = getpass.getuser()
    cmd = (
        f"/bin/bash {shlex.quote(install_script)} "
        f"{shlex.quote(user)} {shlex.quote(helper_src)}"
    )
    apple_script = (
        f'do shell script {json.dumps(cmd)} with administrator privileges'
    )

    try:
        result = subprocess.run(
            ["osascript", "-e", apple_script],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except Exception as e:
        return False, f"Privilege install failed: {e}"

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        return False, err or "Privilege install was cancelled or failed."

    if macos_helper_ready():
        return True, "updated" if (force or outdated) else "installed"
    return False, (
        "Admin approval succeeded, but passwordless WireGuard helper is still unavailable. "
        "Try quitting and relaunching the app."
    )


def run_elevated_startup() -> None:
    """
    Ensure privileges needed for tunnel management.
    Windows: re-launch the whole app elevated (UAC) — required for tunnel services.
    macOS: one-time helper/sudoers install (DMG already did this; source prompts once).
    """
    if IS_WINDOWS:
        if is_admin():
            return
        import ctypes

        params = subprocess.list2cmdline(sys.argv[1:])
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1
        )
        sys.exit(0)

    if IS_MACOS:
        outdated = macos_helper_outdated()
        if macos_helper_ready() and not outdated:
            return
        ok, msg = install_macos_privileges(force=outdated)
        if not ok:
            logger.error("macOS privilege setup failed: %s", msg)
            # Don't abort startup — UI can still open and show the error on Connect
            return
        logger.info("macOS WireGuard privileges ready (%s)", msg)


def run_macos_wg_helper(action: str, config_path: str, timeout: float | None = 90) -> subprocess.CompletedProcess:
    """
    Run up/down/status/restore-dns through the passwordless helper.
    Requires ensure_macos_privileges / DMG install to have succeeded.
    """
    if not os.path.isfile(MACOS_WG_HELPER):
        return subprocess.CompletedProcess(
            args=[MACOS_WG_HELPER, action, config_path],
            returncode=127,
            stdout="",
            stderr="WireGuard helper is not installed",
        )
    return subprocess.run(
        ["sudo", "-n", MACOS_WG_HELPER, action, config_path],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def run_privileged(command: list[str], timeout: float | None = 60) -> subprocess.CompletedProcess:
    """
    Run a command with administrator privileges when required.
    Windows: caller is already elevated at startup.
    macOS: prefer passwordless helper; fall back to a one-shot admin prompt.
    """
    kwargs = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        **subprocess_kwargs(),
    }

    if IS_MACOS and not is_admin():
        # Legacy fallback — prefer run_macos_wg_helper for tunnel ops
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
