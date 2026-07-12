# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)
"""Lightweight checks for cross-platform helpers (no WireGuard / GUI required)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock


class PlatformUtilsTests(unittest.TestCase):
    def test_config_dir_windows(self):
        with mock.patch.dict(os.environ, {"APPDATA": r"C:\Users\Test\AppData\Roaming"}, clear=False):
            import platform_utils as pu
            with mock.patch.object(pu, "IS_WINDOWS", True), mock.patch.object(
                pu, "IS_MACOS", False
            ):
                path = pu.get_config_dir()
        self.assertTrue(path.replace("\\", "/").endswith("AmpliFiTeleport"))

    def test_config_dir_macos(self):
        import platform_utils as pu

        with mock.patch.object(pu, "IS_WINDOWS", False), mock.patch.object(
            pu, "IS_MACOS", True
        ):
            path = pu.get_config_dir()
        self.assertIn("Application Support/AmpliFiTeleport", path.replace("\\", "/"))

    def test_device_platform_constant(self):
        import platform_utils as pu
        import teleport

        self.assertIn(pu.DEVICE_PLATFORM, {"Windows", "macOS", "Linux"})
        # AmpliFi handshake must keep advertising a mobile platform label
        self.assertEqual(teleport.DEVICE_PLATFORM, "iOS")

    def test_wireguard_missing_message_is_os_specific(self):
        import platform_utils as pu

        with mock.patch.object(pu, "IS_MACOS", True), mock.patch.object(
            pu, "IS_WINDOWS", False
        ):
            msg = pu.wireguard_missing_message()
            self.assertIn("brew install", msg)

        with mock.patch.object(pu, "IS_MACOS", False), mock.patch.object(
            pu, "IS_WINDOWS", True
        ):
            msg = pu.wireguard_missing_message()
            self.assertIn("wireguard.com", msg)

    def test_icon_paths_exist(self):
        self.assertTrue(os.path.exists("tray-icon.ico"))
        self.assertTrue(os.path.exists("tray-icon.png"))

    def test_read_config_value(self):
        import tunnel

        with tempfile.TemporaryDirectory() as tmp:
            conf = os.path.join(tmp, "teleport.conf")
            with open(conf, "w", encoding="utf-8") as f:
                f.write("[Interface]\nPrivateKey = abc\nListenPort = 12345\n")
            with mock.patch.object(tunnel, "CONFIG_PATH", conf):
                self.assertEqual(tunnel._read_config_value("PrivateKey"), "abc")
                self.assertEqual(tunnel._read_config_value("ListenPort"), "12345")
                self.assertIsNone(tunnel._read_config_value("Missing"))


class MenuBarHelperLaunchTests(unittest.TestCase):
    def test_frozen_helper_uses_argv_mode_not_script(self):
        import macos_tray as mt

        helper = mt.MenuBarHelper(on_open=lambda: None, on_quit=lambda: None, icon_path=None)
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(
            sys, "executable", "/Apps/AmpliFi.app/Contents/MacOS/AmpliFi"
        ):
            cmd = helper._helper_command()
        self.assertEqual(cmd[0], "/Apps/AmpliFi.app/Contents/MacOS/AmpliFi")
        self.assertIn("--menubar-helper", cmd)
        self.assertTrue(all(not part.endswith("macos_menubar_helper.py") for part in cmd))

    def test_source_helper_uses_script(self):
        import macos_tray as mt

        helper = mt.MenuBarHelper(on_open=lambda: None, on_quit=lambda: None, icon_path=None)
        with mock.patch.object(sys, "frozen", False, create=True), mock.patch.object(
            mt, "_helper_script_path", return_value="/tmp/macos_menubar_helper.py"
        ):
            cmd = helper._helper_command()
        self.assertEqual(cmd[:3], [sys.executable, "-u", "/tmp/macos_menubar_helper.py"])


if __name__ == "__main__":
    # Run from repo root so icon paths resolve
    os.chdir(os.path.dirname(os.path.abspath(__file__)) or ".")
    unittest.main()
