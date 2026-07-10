# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)

import os
import logging
import tkinter as tk

import customtkinter as ctk

from config import TOKEN_FILE, UUID_FILE, CONFIG_PATH, ICON_PATH_ICO, ICON_PATH_PNG
from platform_utils import IS_WINDOWS, corner_radius, ui_font
from tunnel import generate_config, activate_tunnel, deactivate_tunnel, is_tunnel_active
from notifications import show_toast

logger = logging.getLogger("AmpliFi Teleport for Desktop")

# Shared palette — same brand look on both platforms
COLORS = {
    "bg": "#181818",
    "header": "#1a9aff",
    "button": "#1a9aff",
    "button_hover": "#0d6efd",
    "muted_button": "#444444",
    "muted_hover": "#555555",
    "danger": "#e74c3c",
    "danger_hover": "#c0392b",
    "text": "#ffffff",
    "muted_text": "#888888",
    "entry_bg": "#2d2d2d",
}

# Singleton control window so tray / menu-bar can show/hide without nested mainloops
_control_app = {
    "root": None,
    "content_frame": None,
    "icon": None,
    "quit_callback": None,
}


def _set_window_icon(window):
    """Apply the correct window icon API per OS (iconbitmap vs iconphoto)."""
    try:
        if IS_WINDOWS and os.path.exists(ICON_PATH_ICO):
            window.iconbitmap(ICON_PATH_ICO)
            window.after(300, lambda: window.iconbitmap(ICON_PATH_ICO))
        elif os.path.exists(ICON_PATH_PNG):
            icon_image = tk.PhotoImage(file=ICON_PATH_PNG)
            window.iconphoto(True, icon_image)
            window._amplifi_icon_ref = icon_image  # prevent GC
    except Exception:
        logger.debug("Could not set window icon", exc_info=True)


def _center_window(window, width, height):
    window.update_idletasks()
    x = (window.winfo_screenwidth() // 2) - (width // 2)
    y = (window.winfo_screenheight() // 2) - (height // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")


def custom_pin_dialog(parent=None):
    """Custom PIN input dialog with centered label."""
    dialog = ctk.CTkToplevel(parent) if parent else ctk.CTkToplevel()
    dialog.title("Teleport PIN Entry")
    dialog.geometry("350x180")
    dialog.resizable(False, False)
    dialog.configure(fg_color=COLORS["bg"])
    _set_window_icon(dialog)
    _center_window(dialog, 350, 180)

    dialog.transient(parent) if parent else None
    dialog.grab_set()
    dialog.focus_set()

    ctk.CTkLabel(
        dialog,
        text="Enter Teleport PIN",
        font=ui_font(16, "bold"),
        text_color=COLORS["text"],
    ).pack(pady=(20, 5))

    def validate(P):
        return len(P) <= 5

    vcmd = (dialog.register(validate), "%P")

    pin_entry = ctk.CTkEntry(
        dialog,
        width=280,
        height=40,
        font=ui_font(16),
        fg_color=COLORS["entry_bg"],
        text_color=COLORS["text"],
        justify="center",
        validate="key",
        validatecommand=vcmd,
        corner_radius=corner_radius(8),
    )
    pin_entry.pack(pady=(0, 15))
    pin_entry.focus()

    result = [None]

    def submit():
        pin = pin_entry.get().strip()
        if len(pin) != 5:
            ctk.CTkLabel(
                dialog, text="PIN must be exactly 5 characters", text_color="red"
            ).pack(pady=5)
            return
        result[0] = pin
        dialog.destroy()

    def cancel():
        result[0] = None
        dialog.destroy()

    button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
    button_frame.pack(pady=10)

    ctk.CTkButton(
        button_frame,
        text="Cancel",
        width=120,
        fg_color=COLORS["muted_button"],
        hover_color=COLORS["muted_hover"],
        text_color=COLORS["text"],
        corner_radius=corner_radius(10),
        command=cancel,
    ).pack(side="left", padx=10)

    ctk.CTkButton(
        button_frame,
        text="Submit",
        width=120,
        fg_color=COLORS["button"],
        hover_color=COLORS["button_hover"],
        text_color=COLORS["text"],
        corner_radius=corner_radius(10),
        command=submit,
    ).pack(side="right", padx=10)

    dialog.bind("<Return>", lambda _e: submit())
    dialog.bind("<Escape>", lambda _e: cancel())

    dialog.wait_window()
    return result[0]


def custom_confirm_dialog(title, message, parent=None):
    """Custom confirmation dialog."""
    confirm_dialog = ctk.CTkToplevel(parent) if parent else ctk.CTkToplevel()
    confirm_dialog.title(title)
    confirm_dialog.geometry("350x180")
    confirm_dialog.resizable(False, False)
    confirm_dialog.configure(fg_color=COLORS["bg"])
    _set_window_icon(confirm_dialog)
    _center_window(confirm_dialog, 350, 180)

    if parent:
        confirm_dialog.transient(parent)
    confirm_dialog.grab_set()
    confirm_dialog.focus_set()

    ctk.CTkLabel(
        confirm_dialog,
        text=message,
        font=ui_font(14),
        text_color=COLORS["text"],
        wraplength=300,
    ).pack(pady=20)

    button_frame = ctk.CTkFrame(confirm_dialog, fg_color="transparent")
    button_frame.pack(pady=10)

    result = [False]

    def yes():
        result[0] = True
        confirm_dialog.destroy()

    def no():
        result[0] = False
        confirm_dialog.destroy()

    ctk.CTkButton(
        button_frame,
        text="No",
        width=120,
        fg_color=COLORS["muted_button"],
        hover_color=COLORS["muted_hover"],
        text_color=COLORS["text"],
        corner_radius=corner_radius(10),
        command=no,
    ).pack(side="left", padx=10)

    ctk.CTkButton(
        button_frame,
        text="Yes",
        width=120,
        fg_color=COLORS["button"],
        hover_color=COLORS["button_hover"],
        text_color=COLORS["text"],
        corner_radius=corner_radius(10),
        command=yes,
    ).pack(side="right", padx=10)

    confirm_dialog.bind("<Escape>", lambda _e: no())
    confirm_dialog.wait_window()
    return result[0]


def _hide_control_window():
    root = _control_app.get("root")
    if root is not None:
        try:
            root.withdraw()
        except Exception:
            pass


def show_control_window(icon=None, item=None):
    """Show (or re-show) the main control window from the tray / menu bar."""
    if icon is not None:
        _control_app["icon"] = icon

    root = _control_app.get("root")
    if root is None:
        create_control_window(icon=_control_app.get("icon"))
        root = _control_app["root"]

    try:
        root.deiconify()
        root.lift()
        root.focus_force()
        refresh_control_buttons()
    except Exception:
        logger.debug("Could not raise control window", exc_info=True)


def refresh_control_buttons():
    content_frame = _control_app.get("content_frame")
    root = _control_app.get("root")
    if content_frame is None or root is None:
        return

    for widget in content_frame.winfo_children():
        widget.destroy()

    tunnel_active = is_tunnel_active(retries=4, delay=0.8)
    radius = corner_radius(20)

    button_style = {
        "width": 280,
        "height": 50,
        "corner_radius": radius,
        "text_color": COLORS["text"],
        "font": ui_font(14, "bold"),
    }

    def action_and_refresh(action_func):
        action_func(icon=None, item=None)
        # Defer refresh so WireGuard service / wg-quick state can settle (same on both OSes)
        root.after(1500, refresh_control_buttons)

    if not tunnel_active:
        ctk.CTkButton(
            content_frame,
            text="Connect",
            fg_color=COLORS["button"],
            hover_color=COLORS["button_hover"],
            command=lambda: action_and_refresh(on_connect),
            **button_style,
        ).pack(pady=10)

    if tunnel_active:
        ctk.CTkButton(
            content_frame,
            text="Disconnect",
            fg_color=COLORS["button"],
            hover_color=COLORS["button_hover"],
            command=lambda: action_and_refresh(on_disconnect),
            **button_style,
        ).pack(pady=10)

    if (
        os.path.exists(TOKEN_FILE)
        or os.path.exists(UUID_FILE)
        or os.path.exists(CONFIG_PATH)
    ):
        ctk.CTkButton(
            content_frame,
            text="Delete Existing Configuration",
            fg_color=COLORS["button"],
            hover_color=COLORS["button_hover"],
            command=lambda: action_and_refresh(on_delete_config),
            **button_style,
        ).pack(pady=10)

    ctk.CTkButton(
        content_frame,
        text="Quit",
        fg_color=COLORS["danger"],
        hover_color=COLORS["danger_hover"],
        command=quit_application,
        **button_style,
    ).pack(pady=10)


def quit_application(icon=None, item=None):
    """Fully exit the application (tray + window) on both platforms."""
    callback = _control_app.get("quit_callback")
    if callback:
        callback()
        return

    tray = icon or _control_app.get("icon")
    try:
        if tray is not None:
            tray.stop()
    finally:
        root = _control_app.get("root")
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
        os._exit(0)


def create_control_window(icon=None, quit_callback=None):
    """
    Create the singleton control window (does not start mainloop).
    Closing the window hides it to the tray / menu bar instead of quitting.
    """
    if _control_app["root"] is not None:
        return _control_app["root"]

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("AmpliFi Teleport for Desktop")
    root.geometry("350x320")
    root.resizable(False, False)
    root.configure(fg_color=COLORS["bg"])
    _set_window_icon(root)
    _center_window(root, 350, 320)

    header_frame = ctk.CTkFrame(root, fg_color=COLORS["header"], corner_radius=0)
    header_frame.pack(fill="x", pady=(0, 10))

    ctk.CTkLabel(
        header_frame,
        text="AmpliFi Teleport for Desktop",
        font=ui_font(18, "bold"),
        text_color=COLORS["text"],
    ).pack(pady=12)

    content_frame = ctk.CTkFrame(root, fg_color="transparent")
    content_frame.pack(fill="both", expand=True, padx=20, pady=10)

    ctk.CTkLabel(
        root,
        text="Version 1.1.0",
        font=ui_font(10),
        text_color=COLORS["muted_text"],
    ).pack(side="bottom", pady=(0, 10))

    _control_app["root"] = root
    _control_app["content_frame"] = content_frame
    _control_app["icon"] = icon
    _control_app["quit_callback"] = quit_callback

    root.protocol("WM_DELETE_WINDOW", _hide_control_window)
    refresh_control_buttons()
    return root


def open_options_window(icon=None, item=None):
    """
    Backwards-compatible entry: show controls.
    Prefer show_control_window from the tray; this still works for direct calls.
    """
    show_control_window(icon=icon, item=item)
    root = _control_app.get("root")
    if root is not None and _control_app.get("quit_callback") is None:
        # Legacy path when not managed by main.py run loop
        root.mainloop()


def show_pin_dialog(and_activate=True):
    parent = _control_app.get("root")
    pin = custom_pin_dialog(parent=parent)
    if not pin or pin.strip() == "":
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


def on_refresh_config(icon, item):
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


def on_connect(icon, item):
    if not os.path.exists(TOKEN_FILE):
        try:
            return show_pin_dialog(and_activate=True)
        except Exception:
            logger.error("Error While Creating a New Connection", exc_info=True)
            show_toast("Error", "Error Creating New Connection")
            return False, "Error Creating New Connection"
    return on_refresh_config(icon=None, item=None)


def on_disconnect(icon, item):
    if not is_tunnel_active():
        show_toast("Error", "No Teleport Tunnel is active")
        return False, "No Teleport Tunnel is active"

    success, msg = deactivate_tunnel()
    if success:
        show_toast("Status Update", "Teleport disconnected!")
    else:
        show_toast("Error", msg)
    return success, msg


def on_delete_config(icon, item):
    parent = _control_app.get("root")
    if custom_confirm_dialog(
        "Confirm Deletion", "Delete previous Teleport configuration?", parent=parent
    ):
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
