# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)

"""WireGuard tunnel control with identical feature behavior on Windows and macOS."""

from __future__ import annotations

import logging
import os
import re
import time

from config import CONFIG_PATH, TOKEN_FILE, TUNNEL_NAME, UUID_FILE
from platform_utils import (
    IS_MACOS,
    IS_WINDOWS,
    ensure_wireguard_available,
    find_bash,
    find_wg,
    find_wg_quick,
    find_wireguard_exe,
    run_hidden,
    run_privileged,
)
from teleport import connect_device, generate_client_hint, get_device_token

logger = logging.getLogger("AmpliFi Teleport for Desktop")


def generate_config(pin=None):
    """Generate configuration for WireGuard tunnel to AmpliFi Teleport."""
    try:
        ok, msg = ensure_wireguard_available()
        if not ok:
            return False, msg

        if pin:
            if os.path.exists(UUID_FILE):
                with open(UUID_FILE, "r", encoding="utf-8") as f:
                    client_hint = f.read().strip()
            else:
                client_hint = generate_client_hint()
                with open(UUID_FILE, "w", encoding="utf-8") as f:
                    f.write(client_hint)
            device_token = get_device_token(client_hint, pin)
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(device_token)
        else:
            if not os.path.exists(TOKEN_FILE):
                raise Exception("No previous token found. Please enter a new PIN.")
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                device_token = f.read().strip()

        config_str = connect_device(device_token)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(config_str)

        return True, config_str
    except Exception as e:
        logger.error("Error While Creating a New Configuration", exc_info=True)
        return False, str(e)


def activate_tunnel():
    """Activate (or update) the tunnel on the current OS."""
    if not os.path.exists(CONFIG_PATH):
        return False, "No config found. Generate one first."

    ok, msg = ensure_wireguard_available()
    if not ok:
        return False, msg

    try:
        if IS_WINDOWS:
            return _activate_windows()
        if IS_MACOS:
            return _activate_macos()
        return _activate_macos()  # Linux uses wg-quick similarly
    except Exception as e:
        logger.error("Error While Activating Tunnel Connection", exc_info=True)
        return False, f"Activation failed: {e}"


def deactivate_tunnel():
    """Deactivate the AmpliFi Teleport WireGuard tunnel."""
    ok, msg = ensure_wireguard_available()
    if not ok:
        return False, msg

    try:
        if IS_WINDOWS:
            return _deactivate_windows()
        return _deactivate_macos()
    except Exception as e:
        logger.error("Error While Deactivating Tunnel Connection", exc_info=True)
        return False, f"Deactivation failed: {e}"


def is_tunnel_active(retries=3, delay=1.0):
    """Return True when the teleport tunnel is up (same semantics on both OSes)."""
    for _ in range(retries):
        try:
            if IS_WINDOWS:
                active = _is_active_windows()
            else:
                active = _is_active_macos()

            if active:
                logger.info("Teleport Tunnel is active")
                return True

            logger.info("Teleport Tunnel is stopped")
            # Only retry when we got a definitive "not active" — still poll a few times
            # so callers waiting for service state transitions behave the same.
            time.sleep(delay)
        except Exception:
            logger.warning("Error while checking for active tunnel", exc_info=True)
            return False

    return False


# --- Windows (WireGuard tunnel service) -------------------------------------------------

def _activate_windows():
    wg_exe = find_wireguard_exe()
    # Uninstall existing service if present, then install fresh config
    run_hidden([wg_exe, "/uninstalltunnelservice", TUNNEL_NAME])
    result = run_hidden([wg_exe, "/installtunnelservice", CONFIG_PATH], check=False)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        return False, f"Activation failed: {err or result.returncode}"
    return True, "Tunnel activated!"


def _deactivate_windows():
    wg_exe = find_wireguard_exe()
    result = run_hidden([wg_exe, "/uninstalltunnelservice", TUNNEL_NAME], check=False)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip().lower()
        if "not found" in err:
            return False, "Tunnel not active."
        return False, f"Deactivation failed: {(result.stderr or result.stdout or '').strip()}"

    max_wait = 8.0
    poll_interval = 0.8
    elapsed = 0.0
    while elapsed < max_wait:
        if not is_tunnel_active(retries=1, delay=0):
            logger.info("Tunnel successfully deactivated")
            return True, "Tunnel deactivated!"
        time.sleep(poll_interval)
        elapsed += poll_interval

    return True, "Tunnel deactivation requested (status may take a moment to update)"


def _is_active_windows():
    result = run_hidden(
        ["sc", "query", f"WireGuardTunnel${TUNNEL_NAME}"],
        timeout=5,
    )
    output = (result.stdout or "").lower()
    logger.debug("WireGuard Query output: %s", output)

    if result.returncode != 0:
        return False
    if "running" in output:
        return True
    return False


# --- macOS / Unix (wg-quick) ------------------------------------------------------------

def _wg_quick_command(action: str) -> list[str]:
    """
    Build a wg-quick command that works on Apple Silicon and Intel Macs.
    Prefer Homebrew bash because macOS system bash 3.2 breaks wg-quick.
    """
    wg_quick = find_wg_quick()
    bash = find_bash()
    config = CONFIG_PATH

    use_homebrew_bash = bool(
        IS_MACOS
        and bash
        and bash not in ("/bin/bash", "/usr/bin/bash")
    )
    if use_homebrew_bash:
        return [bash, wg_quick, action, config]
    return [wg_quick, action, config]


def _activate_macos():
    # Bring down first so reconnect/refresh replaces the tunnel cleanly (parity with Windows)
    down = run_privileged(_wg_quick_command("down"), timeout=60)
    if down.returncode != 0:
        combined = f"{down.stdout or ''}{down.stderr or ''}".lower()
        # "is not a WireGuard interface" / "does not exist" are fine on first connect
        if not any(
            needle in combined
            for needle in (
                "is not a wireguard interface",
                "does not exist",
                "no such file",
                "unable to access interface",
                "not currently available",
            )
        ):
            logger.debug("wg-quick down before activate: %s", combined.strip())

    up = run_privileged(_wg_quick_command("up"), timeout=90)
    if up.returncode != 0:
        err = (up.stderr or up.stdout or "").strip()
        # osascript wraps stderr into stdout sometimes
        return False, f"Activation failed: {err or up.returncode}"
    return True, "Tunnel activated!"


def _deactivate_macos():
    result = run_privileged(_wg_quick_command("down"), timeout=60)
    if result.returncode != 0:
        err = f"{result.stderr or ''}{result.stdout or ''}".strip().lower()
        if any(
            needle in err
            for needle in (
                "is not a wireguard interface",
                "does not exist",
                "unable to access interface",
                "not currently available",
            )
        ):
            return False, "Tunnel not active."
        return False, f"Deactivation failed: {(result.stderr or result.stdout or '').strip()}"

    max_wait = 8.0
    poll_interval = 0.8
    elapsed = 0.0
    while elapsed < max_wait:
        if not is_tunnel_active(retries=1, delay=0):
            logger.info("Tunnel successfully deactivated")
            return True, "Tunnel deactivated!"
        time.sleep(poll_interval)
        elapsed += poll_interval

    return True, "Tunnel deactivation requested (status may take a moment to update)"


def _is_active_macos():
    """
    Detect our tunnel without requiring root when possible.
    Prefer matching our config's public key so utun-mapped interfaces still count.
    """
    import subprocess

    from platform_utils import subprocess_kwargs

    wg = find_wg()
    if not wg:
        return False

    result = run_hidden([wg, "show", "all", "dump"], timeout=5)
    output = result.stdout or ""
    if result.returncode != 0 or not output.strip():
        priv = run_privileged([wg, "show", "all", "dump"], timeout=15)
        output = priv.stdout or ""

    if not output.strip():
        # Named interface fallback (works when Darwin keeps the config basename)
        named = run_hidden([wg, "show", TUNNEL_NAME], timeout=5)
        if named.returncode == 0 and (named.stdout or "").strip():
            return True
        interfaces = run_hidden([wg, "show", "interfaces"], timeout=5)
        return TUNNEL_NAME in (interfaces.stdout or "").split()

    private_key = _read_config_value("PrivateKey")
    listen_port = _read_config_value("ListenPort")

    if private_key:
        try:
            proc = subprocess.run(
                [wg, "pubkey"],
                input=private_key + "\n",
                capture_output=True,
                text=True,
                timeout=5,
                **subprocess_kwargs(),
            )
            public_key = (proc.stdout or "").strip()
            if public_key and public_key in output:
                return True
        except Exception:
            logger.debug("Could not derive public key for tunnel status check", exc_info=True)

    if listen_port and re.search(rf"\b{re.escape(listen_port)}\b", output):
        return True

    return bool(re.search(rf"(^|\s){re.escape(TUNNEL_NAME)}(\s|$)", output))


def _read_config_value(key: str) -> str | None:
    if not os.path.exists(CONFIG_PATH):
        return None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key} ") or line.startswith(f"{key}="):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        return parts[1].strip()
    except OSError:
        return None
    return None
