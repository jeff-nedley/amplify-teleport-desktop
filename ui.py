# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)

"""Cross-platform UI built with PySide6 (Qt) — identical look on Windows and macOS."""

from __future__ import annotations

import atexit
import logging
import os
import sys
import threading

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
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

# Brand palette derived from tray-icon.png (cyan signal on deep navy)
COLORS = {
    "bg_top": "#EAF2F8",
    "bg_bottom": "#F7FAFC",
    "ink": "#0B2540",
    "ink_soft": "#3D5A73",
    "muted": "#6B8499",
    "line": "#C9D7E4",
    "accent": "#0E8EC8",
    "accent_hover": "#0A7BB0",
    "accent_pressed": "#086A98",
    "accent_soft": "#D7EEF8",
    "connected": "#1F9D6A",
    "connected_soft": "#E3F6EC",
    "disconnected": "#8A9AAB",
    "danger": "#C24747",
    "danger_hover": "#A83B3B",
    "danger_soft": "#F8E8E8",
    "field": "#FFFFFF",
    "field_border": "#B7C9D9",
    "white": "#FFFFFF",
}

APP_STYLESHEET = f"""
QMainWindow, QDialog {{
    background: transparent;
    color: {COLORS["ink"]};
}}
QWidget#central, QWidget#pinRoot {{
    background: transparent;
    color: {COLORS["ink"]};
}}
QLabel {{
    color: {COLORS["ink"]};
    background: transparent;
}}
QLabel#brandTitle {{
    color: {COLORS["ink"]};
    font-size: 26px;
    font-weight: 700;
    letter-spacing: 0.2px;
}}
QLabel#brandSubtitle {{
    color: {COLORS["ink_soft"]};
    font-size: 13px;
    font-weight: 500;
}}
QLabel#statusLabel {{
    font-size: 13px;
    font-weight: 600;
}}
QLabel#versionLabel {{
    color: {COLORS["muted"]};
    font-size: 11px;
}}
QLabel#dialogTitle {{
    color: {COLORS["ink"]};
    font-size: 18px;
    font-weight: 700;
}}
QLabel#dialogHint {{
    color: {COLORS["muted"]};
    font-size: 12px;
}}
QLabel#errorLabel {{
    color: {COLORS["danger"]};
    font-size: 12px;
}}
QPushButton#primaryButton {{
    background-color: {COLORS["accent"]};
    color: {COLORS["white"]};
    border: none;
    border-radius: 12px;
    padding: 14px 18px;
    margin: 0 0 6px 0;
    font-size: 15px;
    font-weight: 700;
    min-height: 24px;
}}
QPushButton#primaryButton:hover {{
    background-color: {COLORS["accent_hover"]};
}}
QPushButton#primaryButton:pressed {{
    background-color: {COLORS["accent_pressed"]};
}}
QPushButton#primaryButton:disabled {{
    background-color: #A9C3D4;
    color: #F4FAFD;
}}
QPushButton#disconnectButton {{
    background-color: {COLORS["danger_soft"]};
    color: {COLORS["danger"]};
    border: 1px solid #E5BDBD;
    border-radius: 12px;
    padding: 14px 18px;
    margin: 0 0 6px 0;
    font-size: 15px;
    font-weight: 700;
    min-height: 24px;
}}
QPushButton#disconnectButton:hover {{
    background-color: #F3DADA;
    color: {COLORS["danger_hover"]};
}}
QPushButton#secondaryButton {{
    background-color: transparent;
    color: {COLORS["ink_soft"]};
    border: 1px solid {COLORS["line"]};
    border-radius: 12px;
    padding: 12px 16px;
    margin: 6px 0 0 0;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#secondaryButton:hover {{
    background-color: {COLORS["accent_soft"]};
    border-color: {COLORS["accent"]};
    color: {COLORS["accent_hover"]};
}}
QPushButton#textButton {{
    background-color: transparent;
    color: {COLORS["muted"]};
    border: none;
    border-radius: 8px;
    padding: 8px 12px;
    margin-top: 10px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#textButton:hover {{
    color: {COLORS["danger"]};
    background-color: {COLORS["danger_soft"]};
}}
QPushButton#mutedButton {{
    background-color: transparent;
    color: {COLORS["ink_soft"]};
    border: 1px solid {COLORS["line"]};
    border-radius: 10px;
    padding: 10px 14px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#mutedButton:hover {{
    background-color: {COLORS["accent_soft"]};
}}
QLineEdit {{
    background-color: {COLORS["field"]};
    color: {COLORS["ink"]};
    border: 1px solid {COLORS["field_border"]};
    border-radius: 10px;
    padding: 12px;
    font-size: 20px;
    font-weight: 600;
    letter-spacing: 6px;
    selection-background-color: {COLORS["accent"]};
    selection-color: {COLORS["white"]};
}}
QLineEdit:focus {{
    border: 1px solid {COLORS["accent"]};
}}
QMessageBox {{
    background-color: {COLORS["bg_bottom"]};
}}
"""


def _ui_font(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    if IS_MACOS:
        font.setFamilies(["Avenir Next", "Avenir", "Gill Sans"])
    elif IS_WINDOWS:
        font.setFamilies(["Bahnschrift", "Segoe UI Variable Display", "Candara"])
    else:
        font.setFamilies(["IBM Plex Sans", "Noto Sans", "DejaVu Sans"])
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


class AtmosphereWidget(QWidget):
    """Soft cool gradient shell — brand atmosphere without flat fill."""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor(COLORS["bg_top"]))
        gradient.setColorAt(0.45, QColor("#F1F6FA"))
        gradient.setColorAt(1.0, QColor(COLORS["bg_bottom"]))
        painter.fillRect(self.rect(), gradient)

        # Quiet top band echoing the logo cyan (not a glow blob).
        band = QLinearGradient(0, 0, self.width(), 0)
        band.setColorAt(0.0, QColor(14, 142, 200, 0))
        band.setColorAt(0.5, QColor(14, 142, 200, 28))
        band.setColorAt(1.0, QColor(14, 142, 200, 0))
        painter.fillRect(0, 0, self.width(), 120, band)


_app_state = {
    "app": None,
    "window": None,
    "tray": None,
}


def _fallback_tray_pixmap(size: int = 64) -> QPixmap:
    """Simple mark so the tray is never given a null icon."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(14, 142, 200))
    pen.setWidth(max(2, size // 16))
    painter.setPen(pen)
    margin = size // 8
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)
    painter.drawEllipse(size // 4, size // 4, size // 2, size // 2)
    painter.end()
    return pix


def _logo_pixmap(logical_size: int = 96) -> QPixmap:
    """
    Load the app logo at device-pixel resolution so Retina/HiDPI stays sharp.
    """
    app = QApplication.instance()
    dpr = float(app.devicePixelRatio() if app is not None else 2.0)
    if dpr < 1.0:
        dpr = 1.0
    pixel_size = max(int(round(logical_size * dpr)), logical_size)

    source = None
    # Prefer PNG; it is a clean 256² asset. Avoid low-res ICO frames.
    if os.path.exists(ICON_PATH_PNG):
        source = QPixmap(ICON_PATH_PNG)
    elif os.path.exists(ICON_PATH_ICO):
        source = QPixmap(ICON_PATH_ICO)

    if source is None or source.isNull():
        fallback = _fallback_tray_pixmap(pixel_size)
        fallback.setDevicePixelRatio(dpr)
        return fallback

    scaled = source.scaled(
        pixel_size,
        pixel_size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled.setDevicePixelRatio(dpr)
    return scaled


def _app_icon() -> QIcon:
    """Application icon from tray-icon.png / .ico (window, Dock, Qt tray)."""
    if IS_WINDOWS and os.path.exists(ICON_PATH_ICO):
        icon = QIcon(ICON_PATH_ICO)
        if not icon.isNull():
            return icon
    if os.path.exists(ICON_PATH_PNG):
        icon = QIcon(ICON_PATH_PNG)
        if not icon.isNull():
            return icon
    if os.path.exists(ICON_PATH_ICO):
        icon = QIcon(ICON_PATH_ICO)
        if not icon.isNull():
            return icon
    return QIcon(_fallback_tray_pixmap())


def _tray_icon() -> QIcon:
    """System tray icon — same artwork as the application icon."""
    icon = _app_icon()
    if icon.isNull():
        icon = QIcon(_fallback_tray_pixmap())
    return icon


def ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        app.setApplicationName("AmpliFi Teleport for Desktop")
        app.setOrganizationName("AmpliFiTeleport")
        app.setWindowIcon(_app_icon())
        app.setStyleSheet(APP_STYLESHEET)
        app.setFont(_ui_font(13))
    _app_state["app"] = app
    return app


class PinDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Teleport PIN")
        self.setModal(True)
        self.setFixedSize(380, 340)
        self.setWindowIcon(_app_icon())

        root = AtmosphereWidget(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

        layout = QVBoxLayout(root)
        root.setObjectName("pinRoot")
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(12)

        logo = QLabel()
        logo.setPixmap(_logo_pixmap(56))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        title = QLabel("Enter Teleport PIN")
        title.setObjectName("dialogTitle")
        title.setFont(_ui_font(18, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        hint = QLabel("Five characters from the AmpliFi mobile app")
        hint.setObjectName("dialogHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)
        layout.addSpacing(6)

        self.pin_entry = QLineEdit()
        self.pin_entry.setMaxLength(5)
        self.pin_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_entry.setPlaceholderText("•••••")
        self.pin_entry.setFont(_ui_font(22, QFont.Weight.DemiBold))
        layout.addWidget(self.pin_entry)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.error_label)
        layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("mutedButton")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        submit_btn = QPushButton("Connect")
        submit_btn.setObjectName("primaryButton")
        submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
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


class TunnelWorker(QThread):
    """Run blocking tunnel / config work off the Qt UI thread."""

    finished_with_result = Signal(bool, str)

    def __init__(self, work_fn, parent=None):
        super().__init__(parent)
        self._work_fn = work_fn

    def run(self):
        try:
            result = self._work_fn()
            if isinstance(result, tuple) and len(result) >= 2:
                ok, msg = result[0], result[1]
            else:
                ok, msg = bool(result), ""
            self.finished_with_result.emit(bool(ok), str(msg or ""))
        except Exception as e:
            logger.exception("Background tunnel operation failed")
            self.finished_with_result.emit(False, str(e))


class ControlWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AmpliFi Teleport")
        self.setFixedSize(400, 520)
        self.setWindowIcon(_app_icon())

        shell = AtmosphereWidget()
        self.setCentralWidget(shell)

        root = QVBoxLayout(shell)
        root.setContentsMargins(28, 32, 28, 20)
        root.setSpacing(0)

        # Brand block — logo is the hero signal
        self.logo_label = QLabel()
        self.logo_label.setPixmap(_logo_pixmap(96))
        self.logo_label.setFixedHeight(104)
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.logo_label)
        root.addSpacing(14)

        brand = QLabel("AmpliFi Teleport")
        brand.setObjectName("brandTitle")
        brand.setFont(_ui_font(26, QFont.Weight.Bold))
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(brand)

        subtitle = QLabel("Secure home network access")
        subtitle.setObjectName("brandSubtitle")
        subtitle.setFont(_ui_font(13, QFont.Weight.Medium))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(subtitle)
        root.addSpacing(22)

        # Status row
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        status_row.addStretch(1)
        self.status_dot = QLabel("●")
        self.status_dot.setFont(_ui_font(12))
        self.status_label = QLabel("Checking…")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setFont(_ui_font(13, QFont.Weight.DemiBold))
        status_row.addWidget(self.status_dot)
        status_row.addWidget(self.status_label)
        status_row.addStretch(1)
        root.addLayout(status_row)
        root.addSpacing(22)

        # Actions
        self.actions_host = QWidget()
        self.actions_host.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.body_layout = QVBoxLayout(self.actions_host)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(16)
        root.addWidget(self.actions_host, stretch=1)

        root.addSpacing(8)
        version = QLabel("Version 1.0.0")
        version.setObjectName("versionLabel")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(version)

        self._busy = False
        self._worker: TunnelWorker | None = None
        self._busy_pulse_on = True
        self._busy_pulse = QTimer(self)
        self._busy_pulse.setInterval(450)
        self._busy_pulse.timeout.connect(self._pulse_busy_indicator)

        self._logo_effect = QGraphicsOpacityEffect(self.logo_label)
        self.logo_label.setGraphicsEffect(self._logo_effect)
        self._logo_anim = QPropertyAnimation(self._logo_effect, b"opacity", self)
        self._logo_anim.setDuration(450)
        self._logo_anim.setStartValue(0.35)
        self._logo_anim.setEndValue(1.0)
        self._logo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.refresh_buttons()

    def showEvent(self, event):
        super().showEvent(event)
        self._logo_anim.stop()
        self._logo_effect.setOpacity(0.35)
        self._logo_anim.start()

    def closeEvent(self, event):
        # Hide to tray instead of quitting
        event.ignore()
        self.hide()
        if IS_MACOS:
            try:
                from macos_tray import hide_dock_icon

                QTimer.singleShot(0, hide_dock_icon)
            except Exception:
                logger.exception("Failed to restore Accessory policy on hide")

    def show_and_raise(self):
        if IS_MACOS:
            try:
                from macos_tray import present_app

                present_app()
            except Exception:
                logger.exception("Failed to present macOS app for window show")

        self.setWindowState(
            self.windowState() & ~Qt.WindowState.WindowMinimized
        )
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        app = QApplication.instance()
        if app is not None:
            app.setActiveWindow(self)
            app.setWindowIcon(_app_icon())
        self.setWindowIcon(_app_icon())
        if not self._busy:
            self.refresh_buttons()
        logger.info("Control window shown/raised (visible=%s)", self.isVisible())

    def _clear_body(self):
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _set_status(self, active: bool):
        if active:
            self.status_dot.setStyleSheet(f"color: {COLORS['connected']};")
            self.status_label.setText("Connected to home network")
            self.status_label.setStyleSheet(f"color: {COLORS['connected']};")
        else:
            self.status_dot.setStyleSheet(f"color: {COLORS['disconnected']};")
            self.status_label.setText("Not connected")
            self.status_label.setStyleSheet(f"color: {COLORS['ink_soft']};")

    def refresh_buttons(self):
        if self._busy:
            return

        self._clear_body()
        active = is_tunnel_active(retries=1, delay=0)
        self._set_status(active)

        self.body_layout.addStretch(1)

        if not active:
            primary = self._add_action_button(
                "Connect", self._on_connect, "primaryButton"
            )
        else:
            primary = self._add_action_button(
                "Disconnect", self._on_disconnect, "disconnectButton"
            )
        primary.setFont(_ui_font(15, QFont.Weight.Bold))

        if (
            os.path.exists(TOKEN_FILE)
            or os.path.exists(UUID_FILE)
            or os.path.exists(CONFIG_PATH)
        ):
            secondary = self._add_action_button(
                "Delete saved configuration",
                self._on_delete_config,
                "secondaryButton",
            )
            secondary.setFont(_ui_font(13, QFont.Weight.DemiBold))

        self.body_layout.addSpacing(4)
        quit_btn = self._add_action_button("Quit AmpliFi Teleport", self._on_quit, "textButton")
        quit_btn.setFont(_ui_font(12, QFont.Weight.DemiBold))

        self.body_layout.addStretch(1)

    def _add_action_button(self, text: str, slot, object_name: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(object_name)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(slot)
        self.body_layout.addWidget(btn)
        return btn

    def _pulse_busy_indicator(self):
        if not self._busy:
            return
        self._busy_pulse_on = not self._busy_pulse_on
        opacity = "1.0" if self._busy_pulse_on else "0.35"
        self.status_dot.setStyleSheet(
            f"color: {COLORS['accent']}; opacity: {opacity};"
        )

    def _set_busy(self, busy: bool, text: str = "Working…"):
        self._busy = busy
        if busy:
            self._clear_body()
            self.status_label.setText(text)
            self.status_label.setStyleSheet(f"color: {COLORS['accent']};")
            self.status_dot.setStyleSheet(f"color: {COLORS['accent']};")
            self._busy_pulse_on = True
            self._busy_pulse.start()

            self.body_layout.addStretch(1)
            hint = QLabel("Please wait — this may take a moment")
            hint.setObjectName("versionLabel")
            hint.setFont(_ui_font(13))
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.body_layout.addWidget(hint)
            self.body_layout.addStretch(1)
        else:
            self._busy_pulse.stop()

    def _run_in_background(
        self,
        status_text: str,
        work_fn,
        *,
        success_toast: tuple[str, str] | None = None,
        show_error_toast: bool = True,
        on_finished=None,
    ):
        """Run blocking tunnel work off the UI thread so status text can paint."""
        if self._busy or (self._worker is not None and self._worker.isRunning()):
            return

        self._set_busy(True, status_text)
        worker = TunnelWorker(work_fn, self)
        self._worker = worker

        def _done(ok: bool, msg: str):
            worker.finished_with_result.disconnect(_done)
            self._set_busy(False)
            if self._worker is worker:
                self._worker = None
            worker.deleteLater()

            if on_finished is not None:
                on_finished(ok, msg)
                return

            if ok and success_toast is not None:
                show_toast(success_toast[0], success_toast[1])
            elif not ok and show_error_toast and msg:
                show_toast("Error", msg)
            if not ok and msg:
                logger.info("Background op result: %s", msg)
            self.refresh_buttons()

        worker.finished_with_result.connect(_done)
        worker.start()

    def _on_connect(self):
        if self._busy:
            return

        if not os.path.exists(TOKEN_FILE):
            pin = ask_pin(self)
            if not pin:
                return

            def work():
                ok, msg = generate_config(pin)
                if not ok:
                    return False, msg
                return activate_tunnel()

            self._run_in_background(
                "Connecting",
                work,
                success_toast=("Status Update", "Teleport connected!"),
            )
            return

        def work():
            ok, msg = generate_config(pin=None)
            if not ok:
                return False, msg
            return activate_tunnel()

        self._run_in_background(
            "Connecting",
            work,
            success_toast=("Status Update", "Teleport connected!"),
        )

    def _on_disconnect(self):
        if self._busy:
            return
        if not is_tunnel_active():
            show_toast("Error", "No Teleport Tunnel is active")
            self.refresh_buttons()
            return

        self._run_in_background(
            "Disconnecting",
            deactivate_tunnel,
            success_toast=("Status Update", "Teleport disconnected!"),
        )

    def _on_delete_config(self):
        if self._busy:
            return
        if not confirm_delete(parent=self):
            return

        def work():
            logger.debug("Disregard following deactivation error if any")
            try:
                deactivate_tunnel()
            except Exception:
                logger.exception("Deactivate during delete (ignored)")
            for path in (TOKEN_FILE, UUID_FILE, CONFIG_PATH):
                if os.path.exists(path):
                    os.remove(path)
            return True, "Configuration Deleted"

        self._run_in_background(
            "Deleting Configuration",
            work,
            success_toast=("Config Update", "Existing configuration deleted!"),
        )

    def _on_quit(self):
        if getattr(self, "_quitting", False):
            return
        self._quitting = True
        self._busy = True

        # Instant perceived exit: dismiss UI / menu bar before cleanup finishes.
        try:
            self.hide()
        except Exception:
            pass
        if IS_MACOS:
            try:
                from macos_tray import hide_dock_icon

                hide_dock_icon()
            except Exception:
                pass
        _stop_tray()

        def work():
            try:
                if is_tunnel_active(retries=1, delay=0):
                    return deactivate_tunnel(for_quit=True)
                return True, "No active tunnel"
            except Exception as e:
                logger.exception("Error while disconnecting tunnel during quit")
                return False, str(e)

        def after(_ok, _msg):
            quit_application(skip_deactivate=True)

        # Prefer a plain worker so we do not rebuild the busy UI on a hidden window.
        if self._worker is not None and self._worker.isRunning():
            # Another op is in flight — force-exit after a short grace period.
            QTimer.singleShot(2500, lambda: quit_application(skip_deactivate=True))
            return

        worker = TunnelWorker(work, self)
        self._worker = worker
        worker.finished_with_result.connect(after)
        worker.start()
        # Hard ceiling so quit never hangs if WireGuard teardown stalls.
        QTimer.singleShot(10000, lambda: quit_application(skip_deactivate=True))


def create_qt_tray(window: ControlWindow) -> QSystemTrayIcon:
    """QSystemTrayIcon — primary on Windows; optional backup on macOS."""
    app = ensure_app()
    icon = _tray_icon()
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("AmpliFi Teleport for Desktop")

    menu = QMenu()
    open_action = QAction("Open Controls", menu)
    quit_action = QAction("Quit", menu)
    menu.addAction(open_action)
    menu.addSeparator()
    menu.addAction(quit_action)

    def _open():
        if IS_MACOS:
            try:
                from macos_tray import present_app

                present_app()
            except Exception:
                pass
        window.show_and_raise()

    open_action.triggered.connect(_open)
    quit_action.triggered.connect(window._on_quit)
    tray.setContextMenu(menu)

    tray._amplifi_menu = menu  # type: ignore[attr-defined]
    tray._amplifi_actions = (open_action, quit_action)  # type: ignore[attr-defined]

    def on_activated(reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            _open()

    tray.activated.connect(on_activated)
    tray.setIcon(icon)
    tray.setVisible(True)
    tray.show()
    logger.info(
        "QSystemTrayIcon shown (null_icon=%s, available=%s, visible=%s)",
        icon.isNull(),
        QSystemTrayIcon.isSystemTrayAvailable(),
        tray.isVisible(),
    )
    return tray


class _MenuBarBridge(QObject):
    """Thread-safe bridge from the menu-bar helper reader → Qt main thread."""

    open_requested = Signal()
    quit_requested = Signal()


def _start_macos_menubar(window: ControlWindow):
    """
    Launch the status item in a separate process.

    Qt and in-process AppKit NSStatusItem fight over NSApplication; a child
    process with its own Cocoa run loop is the reliable approach.
    """
    from macos_tray import MenuBarHelper, hide_dock_icon

    bridge = _MenuBarBridge()
    bridge.open_requested.connect(window.show_and_raise)
    bridge.quit_requested.connect(window._on_quit)
    # Keep the bridge alive for the app lifetime.
    _app_state["menubar_bridge"] = bridge

    helper = MenuBarHelper(
        on_open=lambda: bridge.open_requested.emit(),
        on_quit=lambda: bridge.quit_requested.emit(),
        icon_path=ICON_PATH_PNG if os.path.exists(ICON_PATH_PNG) else None,
    )
    if not helper.start():
        raise RuntimeError("Failed to start macOS menu bar helper process")

    try:
        hide_dock_icon()
    except Exception:
        logger.exception("Failed to hide Dock icon")

    return helper


def start_ui():
    """Create the shared Qt application, main window, and tray / menu bar icon."""
    app = ensure_app()
    window = ControlWindow()
    _app_state["window"] = window
    _app_state["tray"] = None
    atexit.register(_stop_tray)

    if IS_MACOS:
        try:
            helper = _start_macos_menubar(window)
            _app_state["tray"] = helper
            logger.info("Using separate-process macOS menu bar helper")
        except Exception:
            logger.exception(
                "macOS menu bar helper failed; falling back to QSystemTrayIcon"
            )
            _app_state["tray"] = create_qt_tray(window)
            try:
                from macos_tray import hide_dock_icon

                hide_dock_icon()
            except Exception:
                pass
            show_toast(
                "Menu Bar",
                "Started with fallback tray icon. Look near the clock for the app icon.",
            )
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
        # After the first show, return to Accessory so the Dock stays clear.
        def _rehide_dock():
            if window.isVisible():
                # Keep Regular while the window is up so it stays interactive;
                # Dock may briefly show — hide again when the window closes.
                return
            try:
                from macos_tray import hide_dock_icon

                hide_dock_icon()
            except Exception:
                pass

        QTimer.singleShot(500, _rehide_dock)

    return app, window, _app_state.get("tray")


def show_control_window():
    window = _app_state.get("window")
    if window is None:
        start_ui()
        window = _app_state["window"]
    window.show_and_raise()


def _stop_tray():
    """Tear down tray / menu-bar helper so the icon cannot outlive the app."""
    tray = _app_state.pop("tray", None)
    if tray is None:
        return
    try:
        if hasattr(tray, "stop"):
            tray.stop()
        else:
            # QSystemTrayIcon
            try:
                tray.setVisible(False)
            except Exception:
                pass
            try:
                tray.hide()
            except Exception:
                pass
    except Exception:
        logger.exception("Failed to tear down tray / menu bar helper")


def quit_application(skip_deactivate: bool = False):
    """Exit quickly: tear down UI first, disconnect tunnel without blocking the user."""
    if _app_state.get("exiting"):
        _stop_tray()
        os._exit(0)
        return
    _app_state["exiting"] = True

    window = _app_state.get("window")
    if window is not None:
        try:
            window.hide()
        except Exception:
            pass

    # Always drop the tray/menu-bar icon before process exit.
    _stop_tray()

    if not skip_deactivate:
        # Rare sync callers (tests / fallbacks): keep cleanup off the UI feel path.
        def _cleanup_then_exit():
            try:
                logger.info("Quit requested — disconnecting tunnel if active")
                if is_tunnel_active(retries=1, delay=0):
                    success, msg = deactivate_tunnel(for_quit=True)
                    logger.info("Disconnect on quit: success=%s (%s)", success, msg)
            except Exception:
                logger.exception("Error while disconnecting tunnel during quit")
            finally:
                _stop_tray()
                os._exit(0)

        threading.Thread(
            target=_cleanup_then_exit, name="quit-cleanup", daemon=True
        ).start()
        app = _app_state.get("app") or QApplication.instance()
        if app is not None:
            app.quit()
        threading.Timer(10.0, lambda: os._exit(0)).start()
        return

    app = _app_state.get("app") or QApplication.instance()
    if app is not None:
        app.quit()
    threading.Timer(0.25, lambda: os._exit(0)).start()


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
