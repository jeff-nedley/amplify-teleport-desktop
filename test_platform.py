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

    def test_ui_font_families(self):
        import platform_utils as pu

        pu._CACHED_FONT_FAMILY = None
        with mock.patch.object(pu, "IS_MACOS", True), mock.patch.object(
            pu, "IS_WINDOWS", False
        ):
            # Without a live Tk display, helper falls back to the first macOS candidate
            family = pu.ui_font(14, "bold")[0]
            self.assertIn(family, {"Helvetica Neue", "Helvetica", "Lucida Grande", "Arial"})

        pu._CACHED_FONT_FAMILY = None
        with mock.patch.object(pu, "IS_MACOS", False), mock.patch.object(
            pu, "IS_WINDOWS", True
        ):
            family = pu.ui_font(14, "bold")[0]
            self.assertIn(family, {"Segoe UI", "Tahoma", "Arial"})

    def test_device_platform_constant(self):
        import platform_utils as pu

        self.assertIn(pu.DEVICE_PLATFORM, {"Windows", "macOS", "Linux"})

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


if __name__ == "__main__":
    # Run from repo root so icon paths resolve
    os.chdir(os.path.dirname(os.path.abspath(__file__)) or ".")
    unittest.main()
