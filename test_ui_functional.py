# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)
"""Qt control-window functional tests with tunnel operations mocked."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from unittest import mock

# Headless CI / cloud agents
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QPushButton


def _app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication(sys.argv)


def _wait_until(predicate, timeout_s: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout_s
    app = QApplication.instance()
    while time.monotonic() < deadline:
        if app is not None:
            app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _find_button(window, text: str) -> QPushButton | None:
    """Return a button currently in the action layout (ignore deleteLater leftovers)."""
    for index in range(window.body_layout.count()):
        item = window.body_layout.itemAt(index)
        widget = item.widget() if item is not None else None
        if isinstance(widget, QPushButton) and widget.text() == text:
            return widget
    return None


class TempUiPaths:
    def __init__(self, *modules):
        self._modules = modules
        self._tmp = None
        self._patches = []

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = self._tmp.name
        self.paths = {
            "TOKEN_FILE": os.path.join(root, "teleport_token_0"),
            "UUID_FILE": os.path.join(root, "teleport_uuid"),
            "CONFIG_PATH": os.path.join(root, "teleport.conf"),
            "TUNNEL_ACTIVE_MARKER": os.path.join(root, "tunnel_active"),
        }
        for mod in self._modules:
            for name, value in self.paths.items():
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


class ControlWindowFunctionalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def _make_window(self, *, active: bool = False):
        import ui

        with mock.patch.object(ui, "is_tunnel_active", return_value=active), mock.patch.object(
            ui, "IS_MACOS", False
        ):
            window = ui.ControlWindow()
        # Keep window alive for event processing but do not require a display.
        window.show()
        self.app.processEvents()
        return window

    def test_disconnected_shows_connect(self):
        import ui

        with TempUiPaths(ui):
            window = self._make_window(active=False)
            try:
                self.assertIsNotNone(_find_button(window, "Connect"))
                self.assertIsNone(_find_button(window, "Disconnect"))
                self.assertEqual(window.status_label.text(), "Not connected")
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_connected_shows_disconnect(self):
        import ui

        with TempUiPaths(ui) as env:
            with open(env.paths["TOKEN_FILE"], "w", encoding="utf-8") as handle:
                handle.write("token\n")
            window = self._make_window(active=True)
            try:
                self.assertIsNotNone(_find_button(window, "Disconnect"))
                self.assertIsNone(_find_button(window, "Connect"))
                self.assertEqual(window.status_label.text(), "Connected to home network")
                self.assertIsNotNone(_find_button(window, "Delete saved configuration"))
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_connect_with_saved_token_shows_busy_then_connected(self):
        import ui

        with TempUiPaths(ui) as env:
            with open(env.paths["TOKEN_FILE"], "w", encoding="utf-8") as handle:
                handle.write("token\n")

            window = self._make_window(active=False)
            try:
                # After connect completes, report tunnel as active.
                active_state = {"value": False}

                def fake_is_active(**_kwargs):
                    return active_state["value"]

                def fake_generate(pin=None):
                    time.sleep(0.05)
                    return True, "config ok"

                def fake_activate():
                    time.sleep(0.05)
                    active_state["value"] = True
                    return True, "Tunnel activated!"

                with mock.patch.object(
                    ui, "is_tunnel_active", side_effect=fake_is_active
                ), mock.patch.object(
                    ui, "generate_config", side_effect=fake_generate
                ), mock.patch.object(
                    ui, "activate_tunnel", side_effect=fake_activate
                ), mock.patch.object(
                    ui, "ask_pin"
                ) as ask_pin:
                    connect = _find_button(window, "Connect")
                    self.assertIsNotNone(connect)
                    connect.click()
                    self.app.processEvents()

                    self.assertTrue(
                        _wait_until(lambda: window.status_label.text() == "Connecting"),
                        window.status_label.text(),
                    )
                    busy_labels = [
                        label.text()
                        for label in window.findChildren(QLabel)
                        if "Please wait" in label.text()
                    ]
                    self.assertTrue(busy_labels)
                    ask_pin.assert_not_called()

                    self.assertTrue(
                        _wait_until(
                            lambda: (
                                not window._busy
                                and _find_button(window, "Disconnect") is not None
                            ),
                            timeout_s=4.0,
                        ),
                        f"busy={window._busy} status={window.status_label.text()}",
                    )
                    self.assertEqual(
                        window.status_label.text(), "Connected to home network"
                    )
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_connect_first_time_uses_pin_dialog(self):
        import ui

        with TempUiPaths(ui):
            window = self._make_window(active=False)
            try:
                active_state = {"value": False}

                def fake_is_active(**_kwargs):
                    return active_state["value"]

                def fake_generate(pin=None):
                    self.assertEqual(pin, "ABCDE")
                    return True, "config"

                def fake_activate():
                    active_state["value"] = True
                    return True, "up"

                with mock.patch.object(
                    ui, "is_tunnel_active", side_effect=fake_is_active
                ), mock.patch.object(
                    ui, "ask_pin", return_value="ABCDE"
                ), mock.patch.object(
                    ui, "generate_config", side_effect=fake_generate
                ), mock.patch.object(
                    ui, "activate_tunnel", side_effect=fake_activate
                ):
                    _find_button(window, "Connect").click()
                    self.assertTrue(
                        _wait_until(
                            lambda: (
                                not window._busy
                                and _find_button(window, "Disconnect") is not None
                            ),
                            timeout_s=4.0,
                        )
                    )
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_disconnect_returns_to_connect(self):
        import ui

        with TempUiPaths(ui) as env:
            with open(env.paths["TOKEN_FILE"], "w", encoding="utf-8") as handle:
                handle.write("token\n")

            window = self._make_window(active=True)
            try:
                active_state = {"value": True}

                def fake_is_active(**_kwargs):
                    return active_state["value"]

                def fake_deactivate():
                    time.sleep(0.05)
                    active_state["value"] = False
                    return True, "Tunnel deactivated!"

                with mock.patch.object(
                    ui, "is_tunnel_active", side_effect=fake_is_active
                ), mock.patch.object(
                    ui, "deactivate_tunnel", side_effect=fake_deactivate
                ):
                    # Re-bind buttons under the patched is_tunnel_active.
                    window.refresh_buttons()
                    self.app.processEvents()
                    disconnect = _find_button(window, "Disconnect")
                    self.assertIsNotNone(disconnect)
                    disconnect.click()

                    self.assertTrue(
                        _wait_until(lambda: window.status_label.text() == "Disconnecting")
                    )
                    self.assertTrue(
                        _wait_until(
                            lambda: (
                                not window._busy
                                and _find_button(window, "Connect") is not None
                            ),
                            timeout_s=4.0,
                        )
                    )
                    self.assertEqual(window.status_label.text(), "Not connected")
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_delete_configuration_removes_files_and_hides_button(self):
        import ui

        with TempUiPaths(ui) as env:
            for key in ("TOKEN_FILE", "UUID_FILE", "CONFIG_PATH"):
                with open(env.paths[key], "w", encoding="utf-8") as handle:
                    handle.write("x\n")

            window = self._make_window(active=False)
            try:
                with mock.patch.object(
                    ui, "is_tunnel_active", return_value=False
                ), mock.patch.object(
                    ui, "confirm_delete", return_value=True
                ), mock.patch.object(
                    ui, "deactivate_tunnel", return_value=(True, "ok")
                ):
                    window.refresh_buttons()
                    self.app.processEvents()
                    delete = _find_button(window, "Delete saved configuration")
                    self.assertIsNotNone(delete)
                    delete.click()

                    self.assertTrue(
                        _wait_until(
                            lambda: (
                                not window._busy
                                and _find_button(
                                    window, "Delete saved configuration"
                                )
                                is None
                            ),
                            timeout_s=4.0,
                        )
                    )
                    for key in ("TOKEN_FILE", "UUID_FILE", "CONFIG_PATH"):
                        self.assertFalse(os.path.exists(env.paths[key]))
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    # Avoid hanging if a stray timer remains
    app = _app()
    QTimer.singleShot(30_000, app.quit)
    unittest.main()
