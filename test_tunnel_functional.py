# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)
"""Functional tests for tunnel connect / disconnect / config with AmpliFi + WG mocked."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from unittest import mock


SAMPLE_WG_CONFIG = """[Interface]
PrivateKey = AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHHIIIIJJJJKKK=
Address = 10.66.0.2/32
DNS = 1.1.1.1, 8.8.8.8
ListenPort = 51820
PostDown = true

[Peer]
PublicKey = LLLLMMMMNNNNOOOOPPPPQQQQRRRRSSSSTTTTUUUUVVV=
Endpoint = 203.0.113.10:51820
AllowedIPs = 0.0.0.0/0
"""


def _completed(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TempTunnelPaths:
    """Redirect token/config/marker paths into a temporary directory."""

    def __init__(self, *modules):
        self._modules = modules
        self._tmp = None
        self._patches = []

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = self._tmp.name
        paths = {
            "TOKEN_FILE": os.path.join(root, "teleport_token_0"),
            "UUID_FILE": os.path.join(root, "teleport_uuid"),
            "CONFIG_PATH": os.path.join(root, "teleport.conf"),
            "TUNNEL_ACTIVE_MARKER": os.path.join(root, "tunnel_active"),
        }
        self.paths = paths
        self.root = root
        for mod in self._modules:
            for name, value in paths.items():
                if hasattr(mod, name):
                    patch = mock.patch.object(mod, name, value)
                    self._patches.append(patch)
                    patch.start()
        return self

    def __exit__(self, *exc):
        for patch in reversed(self._patches):
            patch.stop()
        if self._tmp is not None:
            self._tmp.cleanup()


class MacosConfigPrepareTests(unittest.TestCase):
    def test_strips_dns_and_writes_sidecar(self):
        import tunnel

        with TempTunnelPaths(tunnel) as env:
            prepared = tunnel._prepare_macos_wg_config(SAMPLE_WG_CONFIG)

            self.assertNotRegex(prepared, r"(?im)^\s*DNS\s*=")
            self.assertNotIn("PostDown", prepared)
            self.assertIn("# AmpliFiTeleportDNS = 1.1.1.1, 8.8.8.8", prepared)
            self.assertIn("[Peer]", prepared)

            sidecar = env.paths["CONFIG_PATH"] + ".dns"
            self.assertTrue(os.path.exists(sidecar))
            with open(sidecar, encoding="utf-8") as handle:
                self.assertEqual(handle.read().strip(), "1.1.1.1 8.8.8.8")


class GenerateConfigFunctionalTests(unittest.TestCase):
    def test_generate_config_with_pin_writes_token_and_conf(self):
        import tunnel

        with TempTunnelPaths(tunnel) as env:
            with mock.patch.object(
                tunnel, "ensure_wireguard_available", return_value=(True, "")
            ), mock.patch.object(
                tunnel, "generate_client_hint", return_value="hint-123"
            ), mock.patch.object(
                tunnel, "get_device_token", return_value="device-token"
            ) as get_token, mock.patch.object(
                tunnel, "connect_device", return_value=SAMPLE_WG_CONFIG
            ) as connect, mock.patch.object(
                tunnel, "IS_MACOS", False
            ), mock.patch.object(
                tunnel, "IS_WINDOWS", True
            ):
                ok, result = tunnel.generate_config(pin="ABCDE")

            self.assertTrue(ok)
            self.assertIn("[Interface]", result)
            get_token.assert_called_once_with("hint-123", "ABCDE")
            connect.assert_called_once_with("device-token")

            with open(env.paths["TOKEN_FILE"], encoding="utf-8") as handle:
                self.assertEqual(handle.read().strip(), "device-token")
            with open(env.paths["UUID_FILE"], encoding="utf-8") as handle:
                self.assertEqual(handle.read().strip(), "hint-123")
            with open(env.paths["CONFIG_PATH"], encoding="utf-8") as handle:
                self.assertIn("PrivateKey", handle.read())

    def test_generate_config_reuses_saved_token_without_pin(self):
        import tunnel

        with TempTunnelPaths(tunnel) as env:
            with open(env.paths["TOKEN_FILE"], "w", encoding="utf-8") as handle:
                handle.write("saved-token\n")

            with mock.patch.object(
                tunnel, "ensure_wireguard_available", return_value=(True, "")
            ), mock.patch.object(
                tunnel, "connect_device", return_value=SAMPLE_WG_CONFIG
            ) as connect, mock.patch.object(
                tunnel, "get_device_token"
            ) as get_token, mock.patch.object(
                tunnel, "IS_MACOS", False
            ):
                ok, _ = tunnel.generate_config(pin=None)

            self.assertTrue(ok)
            connect.assert_called_once_with("saved-token")
            get_token.assert_not_called()

    def test_generate_config_without_token_or_pin_fails(self):
        import tunnel

        with TempTunnelPaths(tunnel):
            with mock.patch.object(
                tunnel, "ensure_wireguard_available", return_value=(True, "")
            ):
                ok, msg = tunnel.generate_config(pin=None)

            self.assertFalse(ok)
            self.assertIn("No previous token", msg)

    def test_generate_config_applies_macos_dns_prep(self):
        import tunnel

        with TempTunnelPaths(tunnel) as env:
            with mock.patch.object(
                tunnel, "ensure_wireguard_available", return_value=(True, "")
            ), mock.patch.object(
                tunnel, "generate_client_hint", return_value="hint"
            ), mock.patch.object(
                tunnel, "get_device_token", return_value="tok"
            ), mock.patch.object(
                tunnel, "connect_device", return_value=SAMPLE_WG_CONFIG
            ), mock.patch.object(
                tunnel, "IS_MACOS", True
            ), mock.patch.object(
                tunnel, "IS_WINDOWS", False
            ):
                ok, conf = tunnel.generate_config(pin="ZZZZZ")

            self.assertTrue(ok)
            self.assertNotRegex(conf, r"(?im)^\s*DNS\s*=")
            self.assertTrue(os.path.exists(env.paths["CONFIG_PATH"] + ".dns"))


class ActivateDeactivateFunctionalTests(unittest.TestCase):
    def test_activate_windows_sets_marker(self):
        import tunnel

        with TempTunnelPaths(tunnel) as env:
            with open(env.paths["CONFIG_PATH"], "w", encoding="utf-8") as handle:
                handle.write(SAMPLE_WG_CONFIG)

            with mock.patch.object(
                tunnel, "ensure_wireguard_available", return_value=(True, "")
            ), mock.patch.object(
                tunnel, "IS_WINDOWS", True
            ), mock.patch.object(
                tunnel, "IS_MACOS", False
            ), mock.patch.object(
                tunnel, "find_wireguard_exe", return_value="C:\\WireGuard\\wireguard.exe"
            ), mock.patch.object(
                tunnel,
                "run_hidden",
                side_effect=[
                    _completed(0),  # uninstall
                    _completed(0),  # install
                ],
            ):
                ok, msg = tunnel.activate_tunnel()

            self.assertTrue(ok)
            self.assertIn("activated", msg.lower())
            self.assertTrue(os.path.exists(env.paths["TUNNEL_ACTIVE_MARKER"]))

    def test_activate_without_config_fails(self):
        import tunnel

        with TempTunnelPaths(tunnel):
            ok, msg = tunnel.activate_tunnel()
            self.assertFalse(ok)
            self.assertIn("No config", msg)

    def test_activate_macos_calls_helper_up(self):
        import tunnel

        with TempTunnelPaths(tunnel) as env:
            with open(env.paths["CONFIG_PATH"], "w", encoding="utf-8") as handle:
                handle.write(SAMPLE_WG_CONFIG)

            helper_calls = []

            def fake_helper(action, config_path, timeout=90):
                helper_calls.append((action, config_path, timeout))
                return _completed(0)

            with mock.patch.object(
                tunnel, "ensure_wireguard_available", return_value=(True, "")
            ), mock.patch.object(
                tunnel, "IS_WINDOWS", False
            ), mock.patch.object(
                tunnel, "IS_MACOS", True
            ), mock.patch.object(
                tunnel, "macos_helper_ready", return_value=True
            ), mock.patch.object(
                tunnel, "_is_active_macos", return_value=False
            ), mock.patch.object(
                tunnel, "run_macos_wg_helper", side_effect=fake_helper
            ):
                ok, msg = tunnel.activate_tunnel()

            self.assertTrue(ok)
            self.assertTrue(any(call[0] == "up" for call in helper_calls))
            self.assertTrue(os.path.exists(env.paths["TUNNEL_ACTIVE_MARKER"]))

    def test_deactivate_windows_clears_marker(self):
        import tunnel

        with TempTunnelPaths(tunnel) as env:
            with open(env.paths["TUNNEL_ACTIVE_MARKER"], "w", encoding="utf-8") as handle:
                handle.write("1\n")

            with mock.patch.object(
                tunnel, "ensure_wireguard_available", return_value=(True, "")
            ), mock.patch.object(
                tunnel, "IS_WINDOWS", True
            ), mock.patch.object(
                tunnel, "IS_MACOS", False
            ), mock.patch.object(
                tunnel, "find_wireguard_exe", return_value="wireguard.exe"
            ), mock.patch.object(
                tunnel, "run_hidden", return_value=_completed(0)
            ), mock.patch.object(
                tunnel, "is_tunnel_active", return_value=False
            ):
                ok, msg = tunnel.deactivate_tunnel()

            self.assertTrue(ok)
            self.assertIn("deactivat", msg.lower())
            self.assertFalse(os.path.exists(env.paths["TUNNEL_ACTIVE_MARKER"]))

    def test_deactivate_macos_calls_helper_down(self):
        import tunnel

        with TempTunnelPaths(tunnel) as env:
            with open(env.paths["TUNNEL_ACTIVE_MARKER"], "w", encoding="utf-8") as handle:
                handle.write("1\n")

            helper_calls = []

            def fake_helper(action, config_path, timeout=90):
                helper_calls.append(action)
                return _completed(0)

            with mock.patch.object(
                tunnel, "ensure_wireguard_available", return_value=(True, "")
            ), mock.patch.object(
                tunnel, "IS_WINDOWS", False
            ), mock.patch.object(
                tunnel, "IS_MACOS", True
            ), mock.patch.object(
                tunnel, "macos_helper_ready", return_value=True
            ), mock.patch.object(
                tunnel, "run_macos_wg_helper", side_effect=fake_helper
            ), mock.patch.object(
                tunnel, "_runtime_tunnel_present", return_value=False
            ):
                ok, msg = tunnel.deactivate_tunnel()

            self.assertTrue(ok)
            self.assertIn("down", helper_calls)
            self.assertIn("restore-dns", helper_calls)
            self.assertFalse(os.path.exists(env.paths["TUNNEL_ACTIVE_MARKER"]))


class DeleteConfigFunctionalTests(unittest.TestCase):
    def test_delete_removes_token_uuid_and_config(self):
        import tunnel
        import ui

        with TempTunnelPaths(tunnel, ui) as env:
            for key in ("TOKEN_FILE", "UUID_FILE", "CONFIG_PATH"):
                with open(env.paths[key], "w", encoding="utf-8") as handle:
                    handle.write("x\n")

            with mock.patch.object(ui, "confirm_delete", return_value=True), mock.patch.object(
                ui, "deactivate_tunnel", return_value=(True, "ok")
            ):
                ok, msg = ui.on_delete_config(parent=None)

            self.assertTrue(ok)
            self.assertEqual(msg, "Configuration Deleted")
            for key in ("TOKEN_FILE", "UUID_FILE", "CONFIG_PATH"):
                self.assertFalse(os.path.exists(env.paths[key]))

    def test_delete_cancelled_leaves_files(self):
        import tunnel
        import ui

        with TempTunnelPaths(tunnel, ui) as env:
            with open(env.paths["TOKEN_FILE"], "w", encoding="utf-8") as handle:
                handle.write("keep\n")

            with mock.patch.object(ui, "confirm_delete", return_value=False):
                ok, msg = ui.on_delete_config(parent=None)

            self.assertFalse(ok)
            self.assertIn("cancelled", msg.lower())
            self.assertTrue(os.path.exists(env.paths["TOKEN_FILE"]))


if __name__ == "__main__":
    unittest.main()
