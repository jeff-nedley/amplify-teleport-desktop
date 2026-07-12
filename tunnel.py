# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)

"""WireGuard tunnel control with identical feature behavior on Windows and macOS."""

from __future__ import annotations

import logging
import os
import re
import time

from config import (
    CONFIG_PATH,
    TOKEN_FILE,
    TUNNEL_ACTIVE_MARKER,
    TUNNEL_NAME,
    UUID_FILE,
)
from platform_utils import (
    IS_MACOS,
    IS_WINDOWS,
    ensure_wireguard_available,
    find_bash,
    find_wg,
    find_wg_quick,
    find_wireguard_exe,
    macos_helper_ready,
    run_hidden,
    run_macos_wg_helper,
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
        if not config_str:
            raise Exception("Teleport handshake failed to produce a WireGuard config.")
        if IS_MACOS:
            config_str = _prepare_macos_wg_config(config_str)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(config_str)

        return True, config_str
    except Exception as e:
        logger.error("Error While Creating a New Configuration", exc_info=True)
        return False, str(e)


def _prepare_macos_wg_config(config: str) -> str:
    """
    Prepare a macOS WireGuard config that does not use DNS=.

    On Darwin, wg-quick's background route monitor can call set_dns() after
    teardown (ALRM race), leaving Wi-Fi connected with a dead tunnel resolver.
    We strip DNS= so the monitor never touches DNS; the privilege helper
    applies/clears DNS itself around up/down.
    """
    dns_values: list[str] = []
    lines: list[str] = []
    for raw in config.splitlines():
        stripped = raw.strip()
        lower = stripped.lower()
        if lower.startswith("postdown"):
            continue
        if lower.startswith("dns ") or lower.startswith("dns="):
            _, _, value = stripped.partition("=")
            for part in value.split(","):
                part = part.strip()
                if part:
                    dns_values.append(part)
            continue
        if lower.startswith("# amplifiteleportdns"):
            continue
        lines.append(raw)

    # Sidecar file read by the helper on up
    dns_sidecar = CONFIG_PATH + ".dns"
    try:
        if dns_values:
            with open(dns_sidecar, "w", encoding="utf-8") as handle:
                handle.write(" ".join(dns_values) + "\n")
        elif os.path.exists(dns_sidecar):
            os.remove(dns_sidecar)
    except OSError:
        logger.debug("Could not write DNS sidecar", exc_info=True)

    out: list[str] = []
    inserted = False
    for line in lines:
        if not inserted and line.strip().startswith("[Peer]"):
            if dns_values:
                out.append(
                    "# AmpliFiTeleportDNS = "
                    + ", ".join(dns_values)
                    + "  # applied by helper (not wg-quick DNS=)"
                )
                out.append("")
            inserted = True
        out.append(line)
    if not inserted and dns_values:
        out.append(
            "# AmpliFiTeleportDNS = "
            + ", ".join(dns_values)
            + "  # applied by helper (not wg-quick DNS=)"
        )

    return "\n".join(out).rstrip() + "\n"


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
        return _activate_macos()
    except Exception as e:
        logger.error("Error While Activating Tunnel Connection", exc_info=True)
        return False, f"Activation failed: {e}"


def deactivate_tunnel(*, for_quit: bool = False):
    """Deactivate the AmpliFi Teleport WireGuard tunnel."""
    ok, msg = ensure_wireguard_available()
    if not ok:
        return False, msg

    try:
        if IS_WINDOWS:
            return _deactivate_windows()
        return _deactivate_macos(for_quit=for_quit)
    except Exception as e:
        logger.error("Error While Deactivating Tunnel Connection", exc_info=True)
        return False, f"Deactivation failed: {e}"


def is_tunnel_active(retries=1, delay=0.0):
    """
    Return True when the teleport tunnel is up.
    Status checks must never prompt for a password (especially on macOS).
    """
    last = False
    for attempt in range(max(1, retries)):
        try:
            if IS_WINDOWS:
                last = _is_active_windows()
            else:
                last = _is_active_macos()

            if last:
                logger.debug("Teleport tunnel is active")
                return True

            if attempt + 1 < retries and delay > 0:
                time.sleep(delay)
        except Exception:
            logger.warning("Error while checking for active tunnel", exc_info=True)
            return False

    logger.debug("Teleport tunnel is stopped")
    return False


def _set_active_marker(active: bool) -> None:
    """Persist UI-facing tunnel state without requiring privileged queries."""
    try:
        if active:
            with open(TUNNEL_ACTIVE_MARKER, "w", encoding="utf-8") as f:
                f.write("1\n")
        elif os.path.exists(TUNNEL_ACTIVE_MARKER):
            os.remove(TUNNEL_ACTIVE_MARKER)
    except OSError:
        logger.debug("Could not update tunnel active marker", exc_info=True)


# --- Windows (WireGuard tunnel service) -------------------------------------------------

def _activate_windows():
    wg_exe = find_wireguard_exe()
    run_hidden([wg_exe, "/uninstalltunnelservice", TUNNEL_NAME])
    result = run_hidden([wg_exe, "/installtunnelservice", CONFIG_PATH], check=False)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        _set_active_marker(False)
        return False, f"Activation failed: {err or result.returncode}"
    _set_active_marker(True)
    return True, "Tunnel activated!"


def _deactivate_windows():
    wg_exe = find_wireguard_exe()
    result = run_hidden([wg_exe, "/uninstalltunnelservice", TUNNEL_NAME], check=False)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip().lower()
        if "not found" in err:
            _set_active_marker(False)
            return False, "Tunnel not active."
        return False, f"Deactivation failed: {(result.stderr or result.stdout or '').strip()}"

    max_wait = 8.0
    poll_interval = 0.8
    elapsed = 0.0
    while elapsed < max_wait:
        if not is_tunnel_active(retries=1, delay=0):
            _set_active_marker(False)
            logger.info("Tunnel successfully deactivated")
            return True, "Tunnel deactivated!"
        time.sleep(poll_interval)
        elapsed += poll_interval

    _set_active_marker(False)
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
    return "running" in output


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
        IS_MACOS and bash and bash not in ("/bin/bash", "/usr/bin/bash")
    )
    if use_homebrew_bash:
        return [bash, wg_quick, action, config]
    return [wg_quick, action, config]


def _activate_macos():
    if not macos_helper_ready():
        return False, (
            "Administrator privileges are not set up for WireGuard. "
            "Quit and relaunch the app to approve the one-time privilege prompt, "
            "or reinstall from the Setup DMG."
        )

    # Rewrite older configs that still use DNS= (triggers the macOS monitor race).
    _migrate_macos_config_dns()

    # Only tear down first when something looks active
    if _is_active_macos():
        down = run_macos_wg_helper("down", CONFIG_PATH, timeout=60)
        if down.returncode != 0:
            combined = f"{down.stdout or ''}{down.stderr or ''}".lower()
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

    up = run_macos_wg_helper("up", CONFIG_PATH, timeout=90)
    if up.returncode != 0:
        err = (up.stderr or up.stdout or "").strip()
        _set_active_marker(False)
        # If up failed, make sure we did not leave tunnel DNS stuck.
        try:
            run_macos_wg_helper("restore-dns", CONFIG_PATH, timeout=45)
        except Exception:
            logger.debug("DNS restore after failed activate", exc_info=True)
        return False, f"Activation failed: {err or up.returncode}"

    _set_active_marker(True)
    return True, "Tunnel activated!"


def _migrate_macos_config_dns() -> None:
    """Strip DNS= from an existing teleport.conf so wg-quick cannot re-break DNS."""
    if not IS_MACOS or not os.path.exists(CONFIG_PATH):
        return
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            original = handle.read()
        if not re.search(r"(?im)^\s*DNS\s*=", original):
            return
        migrated = _prepare_macos_wg_config(original)
        with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
            handle.write(migrated)
        logger.info("Migrated teleport.conf off wg-quick DNS= for macOS safety")
    except OSError:
        logger.debug("Could not migrate macOS WireGuard DNS settings", exc_info=True)


def _deactivate_macos(for_quit: bool = False):
    if not macos_helper_ready():
        return False, (
            "Administrator privileges are not set up for WireGuard. "
            "Quit and relaunch the app to approve the one-time privilege prompt."
        )

    _migrate_macos_config_dns()

    # Quit uses a tighter budget — helper `down` already restores DNS.
    helper_timeout = 20 if for_quit else 90
    result = run_macos_wg_helper("down", CONFIG_PATH, timeout=helper_timeout)

    if not for_quit:
        # Hardened DNS restore (also runs inside helper; repeat here for safety).
        try:
            dns = run_macos_wg_helper("restore-dns", CONFIG_PATH, timeout=45)
            logger.info(
                "DNS restore after disconnect: rc=%s out=%s",
                dns.returncode,
                (dns.stdout or "").strip(),
            )
        except Exception:
            logger.exception("DNS restore after disconnect failed")

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
            _set_active_marker(False)
            return False, "Tunnel not active."
        return False, f"Deactivation failed: {(result.stderr or result.stdout or '').strip()}"

    max_wait = 2.0 if for_quit else 8.0
    poll_interval = 0.4 if for_quit else 0.8
    elapsed = 0.0
    while elapsed < max_wait:
        _set_active_marker(False)
        if not _runtime_tunnel_present():
            logger.info("Tunnel successfully deactivated")
            return True, "Tunnel deactivated!"
        time.sleep(poll_interval)
        elapsed += poll_interval

    _set_active_marker(False)
    return True, "Tunnel deactivation requested (status may take a moment to update)"


def _runtime_tunnel_present() -> bool:
    """
    Unprivileged detection of a live wg-quick tunnel on macOS/Linux.
    wg-quick writes /var/run/wireguard/<name>.name (and often .sock).
    Never prompts for admin.
    """
    runtime_dir = "/var/run/wireguard"
    for suffix in (".name", ".sock"):
        path = os.path.join(runtime_dir, f"{TUNNEL_NAME}{suffix}")
        if os.path.exists(path):
            return True

    wg = find_wg()
    if not wg:
        return False

    # Unprivileged only — do not fall back to run_privileged here
    show = run_hidden([wg, "show", "interfaces"], timeout=5)
    if show.returncode == 0 and TUNNEL_NAME in (show.stdout or "").split():
        return True

    dump = run_hidden([wg, "show", "all", "dump"], timeout=5)
    output = dump.stdout or ""
    if dump.returncode != 0 or not output.strip():
        return False

    private_key = _read_config_value("PrivateKey")
    listen_port = _read_config_value("ListenPort")

    if private_key:
        try:
            import subprocess

            from platform_utils import subprocess_kwargs

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
            logger.debug(
                "Could not derive public key for tunnel status check", exc_info=True
            )

    if listen_port and re.search(rf"\b{re.escape(listen_port)}\b", output):
        return True

    return bool(re.search(rf"(^|\s){re.escape(TUNNEL_NAME)}(\s|$)", output))


def _is_active_macos():
    """
    Status check that never shows an admin password dialog.
    Prefer live runtime evidence; use the connect/disconnect marker only when
    /var/run/wireguard is not readable (some setups lock that directory down).
    """
    if _runtime_tunnel_present():
        return True

    runtime_dir = "/var/run/wireguard"
    marker_on = os.path.exists(TUNNEL_ACTIVE_MARKER)

    if marker_on and (
        not os.path.isdir(runtime_dir)
        or not os.access(runtime_dir, os.R_OK | os.X_OK)
    ):
        return True

    if marker_on:
        # Runtime dir is visible and our tunnel files are gone — clear stale state
        _set_active_marker(False)

    return False


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
