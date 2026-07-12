# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)
"""Checks that macOS installer assets mirror the Windows Inno setup contract."""

from __future__ import annotations

import os
import re
import unittest


ROOT = os.path.dirname(os.path.abspath(__file__))


class MacInstallerParityTests(unittest.TestCase):
    def _read(self, *parts: str) -> str:
        path = os.path.join(ROOT, *parts)
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_required_installer_files_exist(self):
        required = [
            "build_macos_dmg.sh",
            "macos/installer/scripts/postinstall",
            "macos/installer/resources/welcome.html",
            "macos/installer/resources/conclusion.html",
            "macos/uninstaller/Uninstall AmpliFi Teleport.command",
            "app_installer_script.iss",
        ]
        for rel in required:
            self.assertTrue(os.path.exists(os.path.join(ROOT, rel)), rel)

    def test_postinstall_mirrors_innos_wireguard_flow(self):
        post = self._read("macos/installer/scripts/postinstall")
        self.assertIn("is_wireguard_installed", post)
        self.assertIn("WIREGUARD_WAS_MISSING", post)
        self.assertIn("install_wireguard_silently", post)
        self.assertIn("wireguard-tools", post)
        self.assertIn("Launching", post)

    def test_uninstaller_asks_about_wireguard(self):
        uninstall = self._read(
            "macos/uninstaller/Uninstall AmpliFi Teleport.command"
        )
        self.assertIn("Do you also want to uninstall WireGuard?", uninstall)
        self.assertIn("is_wireguard_installed", uninstall)

    def test_inno_still_has_wireguard_silent_install(self):
        iss = self._read("app_installer_script.iss")
        self.assertIn("IsWireGuardInstalled", iss)
        self.assertIn("WireGuardWasMissing", iss)
        self.assertIn("/qn", iss)
        self.assertIn("Do you also want to uninstall WireGuard?", iss)

    def test_dmg_build_script_produces_named_setup_artifact(self):
        script = self._read("build_macos_dmg.sh")
        self.assertIn("Amplifi Teleport For Desktop Setup-", script)
        self.assertIn("productbuild", script)
        self.assertIn("hdiutil", script)
        self.assertIn("postinstall", script)
        self.assertIn('VERSION="$(tr -d', script)

    def test_version_is_centralized(self):
        version_path = os.path.join(ROOT, "VERSION")
        self.assertTrue(os.path.exists(version_path), "VERSION file missing")
        with open(version_path, encoding="utf-8") as handle:
            version = handle.read().strip()
        self.assertRegex(version, r"^\d+\.\d+\.\d+")

        from config import APP_VERSION

        self.assertEqual(APP_VERSION, version)

        iss = self._read("app_installer_script.iss")
        self.assertIn('#include "version.iss"', iss)
        version_iss = self._read("version.iss")
        self.assertIn(f'#define MyAppVersion "{version}"', version_iss)


if __name__ == "__main__":
    unittest.main()
