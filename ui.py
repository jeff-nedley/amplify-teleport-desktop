# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)

"""Cross-platform UI built with PySide6 (Qt) — identical look on Windows and macOS."""

from __future__ import annotations

import logging
import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from config import CONFIG_PATH, ICON_PATH_ICO, ICON_PATH_PNG, TOKEN_FILE, UUID_FILE
from notifications import show_toast
from platform_utils import IS_MACOS, IS_WINDOWS
from tunnel import (
    activate_tunnel,
    deactivate_tunnel,
    generate_config,
    is_tunnel_active,
)

logger = logging.getLogger("AmpliFi Teleport for Desktop")

COLORS = {
    "bg": "#181818",
    "header": "#1a9aff",
    "button": "#1a9aff",
    "button_hover": "#0d6efd",
    "danger": "#e74c3c",
    "danger_hover": "#c0392b",
    "text": "#ffffff",
    "muted_text": "#888888",
    "entry_bg": "#2d2d2d",
    "entry_border": "#3a3a3a",
}

APP_STYLESHEET = f"""
QMainWindow, QDialog, QWidget#central {{
    background-color: {COLORS["bg"]};
    color: {COLORS["text"]};
}}
QLabel {{
    color: {COLORS["text"]};
    background: transparent;
}}
QLabel#headerTitle {{
    color: {COLORS["text"]};
    font-size: 18px;
    font-weight: 700;
}}
QLabel#versionLabel {{
    color: {COLORS["muted_text"]};
    font-size: 11px;
}}
QLabel#dialogTitle {{
    font-size: 16px;
    font-weight: 700;
}}
QFrame#headerBar {{
    background-color: {COLORS["header"]};
}}
QPushButton {{
    background-color: {COLORS["button"]};
    color: {COLORS["text"]};
    border: none;
    border-radius: 14px;
    padding: 14px 16px;
    font-size: 14px;
    font-weight: 700;
    min-height: 22px;
}}
QPushButton:hover {{
    background-color: {COLORS["button_hover"]};
}}
QPushButton:disabled {{
    background-color: #555555;
    color: #aaaaaa;
}}
QPushButton#dangerButton {{
    background-color: {COLORS["danger"]};
}}
QPushButton#dangerButton:hover {{
    background-color: {COLORS["danger_hover"]};
}}
QPushButton#mutedButton {{
    background-color: #444444;
}}
QPushButton#mutedButton:hover {{
    background-color: #555555;
}}
QLineEdit {{
    background-color: {COLORS["entry_bg"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["entry_border"]};
    border-radius: 8px;
    padding: 10px;
    font-size: 16px;
    selection-background-color: {COLORS["header"]};
}}
QMessageBox {{
    background-color: {COLORS["bg"]};
}}
"""

_app_state = {
    "app": None,
    "window": None,
    "tray": None,
}


def _fallback_tray_pixmap(size: int = 64) -> QPixmap:
    """Simple black-on-transparent mark so the tray is never given a null icon."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(0, 0, 0))
    pen.setWidth(max(2, size // 16))
    painter.setPen(pen)
    margin = size // 8
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)
    painter.drawEllipse(
        size // 4, size // 4, size // 2, size // 2
    )
    painter.end()
    return pix


def _app_icon() -> QIcon:
    if IS_WINDOWS and os.path.exists(ICON_PATH_ICO):
        icon = QIcon(ICON_PATH_ICO)
        if not icon.isNull():
            return icon
    if os.path.exists(ICON_PATH_PNG):
        icon = QIcon(ICON_PATH_PNG)
        if not icon.isNull():
            return icon
    return QIcon(_fallback_tray_pixmap())


def _tray_icon() -> QIcon:
    """Icon for the system tray / menu bar — never null; mask on macOS."""
    icon = _app_icon()
    if icon.isNull():
        icon = QIcon(_fallback_tray_pixmap())
    if IS_MACOS:
        # Lets macOS tint the glyph for light/dark menu bars.
        icon.setIsMask(True)
    return icon


def ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        # High-DPI friendly defaults
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        app.setApplicationName("AmpliFi Teleport for Desktop")
        app.setOrganizationName("AmpliFiTeleport")
        app.setWindowIcon(_app_icon())
        app.setStyleSheet(APP_STYLESHEET)
        # Prefer a cross-platform font that Qt maps well on Win/Mac
        app.setFont(QFont("Segoe UI" if IS_WINDOWS else "Helvetica Neue", 13))
    _app_state["app"] = app
    return app


class PinDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Teleport PIN Entry")
        self.setModal(True)
        self.setFixedSize(350, 200)
        self.setWindowIcon(_app_icon())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("Enter Teleport PIN")
        title.setObjectName("dialogTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.pin_entry = QLineEdit()
        self.pin_entry.setMaxLength(5)
        self.pin_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_entry.setPlaceholderText("•••••")
        layout.addWidget(self.pin_entry)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #ff5555;")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("mutedButton")
        cancel_btn.clicked.connect(self.reject)
        submit_btn = QPushButton("Submit")
        submit_btn.clicked.connect(self._submit)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(submit_btn)
        layout.addLayout(buttons)

        self.pin_entry.returnPressed.connect(self._submit)
        self.pin_entry.setFocus()

    def _submit(self):
        pin = self.pin_entry.text().strip()
        if len(pin) != 5:
            self.error_label.setText("PIN must be exactly 5 characters")
            return
        self.accept()

    def pin_value(self) -> str | None:
        if self.result() == QDialog.DialogCode.Accepted:
            return self.pin_entry.text().strip()
        return None


class ControlWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AmpliFi Teleport for Desktop")
        self.setFixedSize(350, 340)
        self.setWindowIcon(_app_icon())

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("headerBar")
        header.setFixedHeight(52)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("AmpliFi Teleport for Desktop")
        title.setObjectName("headerTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title)
        root.addWidget(header)

        body = QWidget()
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(24, 16, 24, 8)
        self.body_layout.setSpacing(10)
        self.body_layout.addStretch(1)
        root.addWidget(body, stretch=1)

        version = QLabel("Version 1.0.0")
        version.setObjectName("versionLabel")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(version)
        root.addSpacing(8)

        self._busy = False
        self.refresh_buttons()

    def closeEvent(self, event):
        # Hide to tray instead of quitting
        event.ignore()
        self.hide()

    def show_and_raise(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.refresh_buttons()

    def _clear_body(self):
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def refresh_buttons(self):
        self._clear_body()
        self.body_layout.addStretch(1)

        active = is_tunnel_active(retries=1, delay=0)

        if not active:
            self._add_action_button("Connect", self._on_connect)
        else:
            self._add_action_button("Disconnect", self._on_disconnect)

        if (
            os.path.exists(TOKEN_FILE)
            or os.path.exists(UUID_FILE)
            or os.path.exists(CONFIG_PATH)
        ):
            self._add_action_button(
                "Delete Existing Configuration", self._on_delete_config
            )

        quit_btn = self._add_action_button("Quit", self._on_quit)
        quit_btn.setObjectName("dangerButton")
        # Re-apply stylesheet object name styles
        quit_btn.style().unpolish(quit_btn)
        quit_btn.style().polish(quit_btn)

        self.body_layout.addStretch(1)

    def _add_action_button(self, text: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(slot)
        self.body_layout.addWidget(btn)
        return btn

    def _set_busy(self, busy: bool):
        self._busy = busy
        for i in range(self.body_layout.count()):
            widget = self.body_layout.itemAt(i).widget()
            if isinstance(widget, QPushButton):
                widget.setEnabled(not busy)

    def _after_action_refresh(self):
        self._set_busy(False)
        self.refresh_buttons()

    def _on_connect(self):
        if self._busy:
            return
        self._set_busy(True)
        QApplication.processEvents()
        try:
            ok, msg = on_connect()
            if not ok and msg:
                logger.info("Connect result: %s", msg)
        finally:
            QTimer.singleShot(1200, self._after_action_refresh)

    def _on_disconnect(self):
        if self._busy:
            return
        self._set_busy(True)
        QApplication.processEvents()
        try:
            on_disconnect()
        finally:
            QTimer.singleShot(1200, self._after_action_refresh)

    def _on_delete_config(self):
        if self._busy:
            return
        self._set_busy(True)
        QApplication.processEvents()
        try:
            on_delete_config(parent=self)
        finally:
            QTimer.singleShot(800, self._after_action_refresh)

    def _on_quit(self):
        quit_application()


def create_qt_tray(window: ControlWindow) -> QSystemTrayIcon:
    """QSystemTrayIcon for Windows (and macOS fallback)."""
    tray = QSystemTrayIcon(_tray_icon(), window)
    tray.setToolTip("AmpliFi Teleport for Desktop")

    # Parent menu to the window so Qt owns the lifetime (avoids GC drops).
    menu = QMenu(window)
    open_action = QAction("Open Controls", menu)
    open_action.triggered.connect(window.show_and_raise)
    quit_action = QAction("Quit", menu)
    quit_action.triggered.connect(quit_application)
    menu.addAction(open_action)
    menu.addSeparator()
    menu.addAction(quit_action)
    tray.setContextMenu(menu)

    def on_activated(reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            window.show_and_raise()

    tray.activated.connect(on_activated)
    tray.setVisible(True)
    tray.show()
    logger.info(
        "QSystemTrayIcon shown (null_icon=%s, available=%s)",
        _tray_icon().isNull(),
        QSystemTrayIcon.isSystemTrayAvailable(),
    )
    return tray


def create_macos_tray(window: ControlWindow):
    """
    Native AppKit status item (menu bar) + hide Dock icon.

    start() is deferred via QTimer — creating the status item before Qt's
    Cocoa event loop is running often yields button()=None and no icon.
    """
    from macos_tray import MacOSTray

    MacOSTray.hide_dock_icon()

    tray = MacOSTray(
        on_open=window.show_and_raise,
        on_quit=quit_application,
        title="AmpliFi Teleport for Desktop",
        icon_path=ICON_PATH_PNG if os.path.exists(ICON_PATH_PNG) else None,
    )
    return tray


def start_ui():
    """Create the shared Qt application, main window, and tray / menu bar icon."""
    app = ensure_app()

    if IS_MACOS:
        try:
            from macos_tray import MacOSTray

            MacOSTray.hide_dock_icon()
        except Exception:
            logger.exception("Failed to set macOS accessory activation policy")

    window = ControlWindow()
    _app_state["window"] = window
    _app_state["tray_fallback"] = None

    if IS_MACOS:
        # Show a Qt tray icon immediately so the menu bar is never empty while
        # the native AppKit status item is deferred/retried.
        qt_tray = create_qt_tray(window)
        _app_state["tray_fallback"] = qt_tray

        try:
            native = create_macos_tray(window)
            _app_state["tray"] = native

            def _on_native_ready():
                # Prefer the native “AT” status item; hide the Qt duplicate.
                fb = _app_state.get("tray_fallback")
                if isinstance(fb, QSystemTrayIcon):
                    fb.hide()
                    logger.info("Hid Qt tray after native status item became ready")

            def _schedule_with_hide():
                retry_delays_ms = (0, 100, 250, 500, 1000, 2000)

                def attempt(index: int = 0):
                    if native.is_running:
                        _on_native_ready()
                        return
                    ok = False
                    try:
                        ok = bool(native.start())
                    except Exception:
                        logger.exception("macOS status item start failed")
                    if ok:
                        logger.info("macOS menu bar status item is up")
                        _on_native_ready()
                        return
                    next_index = index + 1
                    if next_index < len(retry_delays_ms):
                        delay = retry_delays_ms[next_index] - retry_delays_ms[index]
                        QTimer.singleShot(
                            max(delay, 1), lambda i=next_index: attempt(i)
                        )
                        return
                    logger.warning(
                        "Native status item did not start; keeping Qt tray icon"
                    )

                QTimer.singleShot(retry_delays_ms[0], lambda: attempt(0))

            _schedule_with_hide()
        except Exception:
            logger.exception(
                "Failed to init macOS AppKit status item; Qt tray remains active"
            )
            _app_state["tray"] = qt_tray
    else:
        tray = create_qt_tray(window)
        _app_state["tray"] = tray
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray is not available on this desktop session")
            show_toast(
                "Tray Unavailable",
                "System tray is unavailable; the control window will stay open.",
            )

    window.show_and_raise()

    if IS_MACOS:

        def _reassert_accessory():
            try:
                from macos_tray import MacOSTray

                MacOSTray.hide_dock_icon()
            except Exception:
                pass

        QTimer.singleShot(0, _reassert_accessory)
        QTimer.singleShot(500, _reassert_accessory)
        QTimer.singleShot(1500, _reassert_accessory)

    return app, window, _app_state.get("tray")


def show_control_window():
    window = _app_state.get("window")
    if window is None:
        start_ui()
        window = _app_state["window"]
    window.show_and_raise()


def quit_application():
    for key in ("tray", "tray_fallback"):
        tray = _app_state.get(key)
        if tray is None:
            continue
        try:
            if hasattr(tray, "stop"):
                tray.stop()
            elif hasattr(tray, "hide"):
                tray.hide()
        except Exception:
            logger.exception("Failed to tear down tray / status item (%s)", key)
    app = _app_state.get("app") or QApplication.instance()
    if app is not None:
        app.quit()
    # Ensure process exits even if background work remains
    QTimer.singleShot(200, lambda: os._exit(0))


def ask_pin(parent=None) -> str | None:
    dialog = PinDialog(parent)
    dialog.exec()
    return dialog.pin_value()


def confirm_delete(parent=None) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle("Confirm Deletion")
    box.setIcon(QMessageBox.Icon.Question)
    box.setText("Delete previous Teleport configuration?")
    box.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    box.setDefaultButton(QMessageBox.StandardButton.No)
    return box.exec() == QMessageBox.StandardButton.Yes


def show_pin_dialog(and_activate=True, parent=None):
    pin = ask_pin(parent)
    if not pin:
        return False, "No PIN entered."

    success, msg = generate_config(pin)
    if not success:
        show_toast("Error", msg)
        return False, msg

    if and_activate:
        act_success, act_msg = activate_tunnel()
        if act_success:
            show_toast("Status Update", "Teleport connected!")
            return True, "Tunnel connected successfully"
        show_toast("Error", act_msg)
        return False, act_msg

    show_toast("Config Update", "Teleport configuration updated!")
    return True, "Config generated successfully"


def on_refresh_config():
    if not os.path.exists(TOKEN_FILE):
        show_toast("Error", "No previous configuration. Enter a PIN first.")
        return False, "No previous configuration"
    success, msg = generate_config(pin=None)
    if success:
        act_success, act_msg = activate_tunnel()
        if act_success:
            show_toast("Status Update", "Teleport connected!")
        else:
            show_toast("Error", act_msg)
        return act_success, act_msg

    logger.error(
        "Error While Refreshing Configuration for a New Connection", exc_info=True
    )
    show_toast("Error", f"Refresh failed: {msg}")
    return success, msg


def on_connect():
    parent = _app_state.get("window")
    if not os.path.exists(TOKEN_FILE):
        try:
            return show_pin_dialog(and_activate=True, parent=parent)
        except Exception:
            logger.error("Error While Creating a New Connection", exc_info=True)
            show_toast("Error", "Error Creating New Connection")
            return False, "Error Creating New Connection"
    return on_refresh_config()


def on_disconnect():
    if not is_tunnel_active():
        show_toast("Error", "No Teleport Tunnel is active")
        return False, "No Teleport Tunnel is active"

    success, msg = deactivate_tunnel()
    if success:
        show_toast("Status Update", "Teleport disconnected!")
    else:
        show_toast("Error", msg)
    return success, msg


def on_delete_config(parent=None):
    parent = parent or _app_state.get("window")
    if confirm_delete(parent=parent):
        try:
            logger.debug("Disregard following deactivation error if any")
            deactivate_tunnel()
            for path in (TOKEN_FILE, UUID_FILE, CONFIG_PATH):
                if os.path.exists(path):
                    os.remove(path)
            show_toast("Config Update", "Existing configuration deleted!")
            return True, "Configuration Deleted"
        except Exception as e:
            logger.error("Error While Deleting Existing Configuration", exc_info=True)
            show_toast("Error", f"Deletion failed: {str(e)}")
            return False, "Error while deleting configuration"
    return False, "Deletion cancelled"
