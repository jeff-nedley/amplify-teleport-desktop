# tray_app.py
import asyncio
import logging
import os
import sys
import subprocess
import time
import ctypes
import customtkinter as ctk
import pystray
from PIL import Image
import tkinter as tk
from tkinter import simpledialog, messagebox, Text, Toplevel, Scrollbar, END, ttk
from teleport import connect_device, get_device_token, generate_client_hint

# Config paths (store in appdata to persist)
CONFIG_DIR = os.path.join(os.getenv('APPDATA'), 'AmpliFiTeleport')
os.makedirs(CONFIG_DIR, exist_ok=True)
UUID_FILE = os.path.join(CONFIG_DIR, 'teleport_uuid')
TOKEN_FILE = os.path.join(CONFIG_DIR, 'teleport_token_0')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'teleport.conf')  # Fixed name for consistent tunnel name 'teleport'

# WireGuard CLI path (assume in PATH; or set full path e.g., r'C:\Program Files\WireGuard\wireguard.exe')
WG_EXE = 'wireguard.exe'

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_elevated():
    """Relaunch as admin if not already."""
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit(0)

def generate_config(pin=None):
    """Mirror original main.py logic to generate WireGuard config."""
    try:
        if pin:
            # Generate or load UUID
            if os.path.exists(UUID_FILE):
                with open(UUID_FILE, 'r') as f:
                    client_hint = f.read().strip()
            else:
                client_hint = generate_client_hint()
                with open(UUID_FILE, 'w') as f:
                    f.write(client_hint)
            device_token = get_device_token(client_hint, pin)
            with open(TOKEN_FILE, 'w') as f:
                f.write(device_token)
        else:
            if not os.path.exists(TOKEN_FILE):
                raise Exception("No previous token found. Please enter a new PIN.")
            with open(TOKEN_FILE, 'r') as f:
                device_token = f.read().strip()
        config_str = connect_device(device_token)
        with open(CONFIG_PATH, 'w') as f:
            f.write(config_str)
        return True, config_str
    except Exception as e:
        return False, str(e)

def activate_tunnel():
    """Activate (or update) the tunnel: uninstall if exists, then install new."""
    if not os.path.exists(CONFIG_PATH):
        return False, "No config found. Generate one first."
    try:
        # Uninstall existing if present (ignore error if not)
        subprocess.run([WG_EXE, '/uninstalltunnelservice', 'teleport'], capture_output=True)
        # Install/activate
        subprocess.run([WG_EXE, '/installtunnelservice', CONFIG_PATH], check=True, capture_output=True)
        return True, "Tunnel activated!"
    except subprocess.CalledProcessError as e:
        return False, f"Activation failed: {e.stderr.decode()}"

def deactivate_tunnel():
    try:
        subprocess.run([WG_EXE, '/uninstalltunnelservice', 'teleport'], check=True, capture_output=True)
        
        # Poll until service is gone or stopped
        max_wait = 8.0
        poll_interval = 0.8
        elapsed = 0.0
        while elapsed < max_wait:
            if not is_tunnel_active():
                return True, "Tunnel deactivated!"
            time.sleep(poll_interval)
            elapsed += poll_interval
        
        return True, "Tunnel deactivation requested (status may take a moment to update)"
    except subprocess.CalledProcessError as e:
        if 'not found' in e.stderr.decode().lower():
            return False, "Tunnel not active."
        return False, f"Deactivation failed: {e.stderr.decode()}"
    
def is_tunnel_active(retries=3, delay=1.0):
    """Check if the 'teleport' tunnel service is running (active)."""
    for attempt in range(retries):
        try:
            result = subprocess.run(
                ['sc', 'query', 'WireGuardTunnel$teleport'],
                capture_output=True,
                text=True,
                timeout=5
            )
            output = result.stdout.lower()

            if result.returncode == 0:
                if 'running' in output:
                    return True
                if 'stopped' in output or '1  stopped' in output:
                    return False
                return False  # pending or unknown

            return False  # service not found

        except (subprocess.TimeoutExpired, FileNotFoundError):
            logging.warning("Could not query service")
            return False
        except Exception as e:
            logging.warning(f"Tunnel check failed: {str(e)}")
            return False

        # If we got here, retry after delay (helps catch post-uninstall lag)
        time.sleep(delay)

    return False  # After all retries, assume not active

def show_pin_dialog(and_activate=True):
    """Prompt for PIN, generate config, optionally activate."""
    root = tk.Tk()
    root.withdraw()
    pin = simpledialog.askstring("AmpliFi Teleport", "Enter your Teleport PIN (e.g., AB123):")
    root.destroy()
    if pin:
        success, msg = generate_config(pin)
        if success:
            if and_activate:
                act_success, act_msg = activate_tunnel()
                messagebox.showinfo("Result", act_msg if act_success else f"Error: {act_msg}")
            else:
                messagebox.showinfo("Result", "Config generated successfully!")
        else:
            messagebox.showerror("Error", f"Generation failed: {msg}")

def on_refresh_config(icon, item):
    if not os.path.exists(TOKEN_FILE):
        messagebox.showerror("Error", "No previous configuration. Enter a PIN first.")
        return
    success, msg = generate_config(pin=None)
    if success:
        act_success, act_msg = activate_tunnel()
        messagebox.showinfo("Result", act_msg if act_success else f"Error: {act_msg}")
        return act_success, act_msg
    else:
        messagebox.showerror("Error", f"Refresh failed: {msg}")
        return success, msg

def on_connect(icon, item):
    if not os.path.exists(TOKEN_FILE):
        try:
            show_pin_dialog(and_activate=True)
            return True, "Successfully Created New Connection"
        except Exception as e:
            return False, "Error Creating New Connection"
    else:
        return on_refresh_config(icon=None, item=None)

def on_disconnect(icon, item):
    if not is_tunnel_active:
        messagebox.showerror("Error", "No Teleport Tunnel is active")
        return False, "No Teleport Tunnel is active"
    else:
        success, msg = deactivate_tunnel()
        messagebox.showinfo("Tunnel", msg if success else f"Error: {msg}")
        return success, msg

def on_delete_config(icon, item):
    if messagebox.askyesno("Confirm", "Delete previous configuration and reset?"):
        try:
            deactivate_tunnel()  # Ignore result
            if os.path.exists(TOKEN_FILE):
                os.remove(TOKEN_FILE)
            if os.path.exists(UUID_FILE):
                os.remove(UUID_FILE)
            if os.path.exists(CONFIG_PATH):
                os.remove(CONFIG_PATH)
            messagebox.showinfo("Deleted", "Configuration deleted. You can now enter a new PIN.")
            return True, "Configuration Deleted"
        except Exception as e:
            messagebox.showerror("Error", f"Deletion failed: {str(e)}")
            return False, "Error while deleting configuration"

def open_options_window(icon=None, item=None):
    """Opens a modern CustomTkinter window with rounded gradient buttons."""
    ctk.set_appearance_mode("dark")  # Matches your #181818 dark theme
    ctk.set_default_color_theme("blue")  # Base theme - can be "green", "dark-blue", etc.

    root = ctk.CTk()
    root.title("AmpliFi Teleport for Desktop")
    root.geometry("350x320")
    root.resizable(False, False)
    root.attributes('-topmost', True)
    root.configure(bg="#181818")

    # Header frame 
    header_frame = ctk.CTkFrame(root, fg_color="#1a9aff", corner_radius=0)
    header_frame.pack(fill="x", pady=(0, 10))

    header_label = ctk.CTkLabel(
        header_frame,
        text="AmpliFi Teleport for Desktop",
        font=("Arial", 18, "bold"),
        text_color="white"
    )
    header_label.pack(pady=12)

    # Main content frame
    content_frame = ctk.CTkFrame(root, fg_color="transparent")
    content_frame.pack(fill="both", expand=True, padx=20, pady=10)

    def refresh_buttons():
        # Clear previous buttons
        for widget in content_frame.winfo_children():
            widget.destroy()

        tunnel_active = is_tunnel_active(retries=4, delay=0.8)

        # Custom button style with gradient-like hover
        button_style = {
            "width": 280,
            "height": 50,
            "corner_radius": 20,
            "text_color": "white",
            "font": ("Arial", 14, "bold")
        }

        if not tunnel_active:
            ctk.CTkButton(
                content_frame,
                text="Connect",
                fg_color="#1a9aff",
                hover_color="#0d6efd",
                command=lambda: action_and_refresh(on_connect),
                **button_style
            ).pack(pady=10)

        if tunnel_active:
            ctk.CTkButton(
                content_frame,
                text="Disconnect",
                fg_color="#1a9aff",
                hover_color="#0d6efd",
                command=lambda: action_and_refresh(on_disconnect),
                **button_style
            ).pack(pady=10)

        if os.path.exists(TOKEN_FILE) or os.path.exists(UUID_FILE) or os.path.exists(CONFIG_PATH):
            ctk.CTkButton(
                content_frame,
                text="Delete Existing Configuration",
                fg_color="#1a9aff",
                hover_color="#0d6efd",
                command=lambda: action_and_refresh(on_delete_config),
                **button_style
            ).pack(pady=10)

        # Quit button (same style)
        ctk.CTkButton(
            content_frame,
            text="Quit",
            fg_color="#e74c3c",
            hover_color="#c0392b",
            command=lambda: sys.exit(0),
            **button_style
        ).pack(pady=10)

        # Version label
        ctk.CTkLabel(
            root,
            text="Version 1.0.0",
            font=("Arial", 10),
            text_color="#888888"
        ).pack(side="bottom", pady=(0, 10))

    def action_and_refresh(action_func):
        success, msg = action_func(icon=None, item=None)

        if action_func is on_disconnect:
            time.sleep(2.0)

        refresh_buttons()

    refresh_buttons()
    root.mainloop()

def main():
    run_elevated()  # Keep admin elevation

    # Removed: no auto-PIN prompt or connection on launch
    # User must left-click tray icon → open window → click Connect to trigger PIN if needed

    image = Image.open("tray-icon.ico")

    # Right-click menu (unchanged)
    menu = pystray.Menu(
        pystray.MenuItem("Connect", on_connect),
        pystray.MenuItem("Disconnect", on_disconnect),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Delete Existing Configuration", on_delete_config),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", lambda: [icon.stop(), sys.exit(0)])
    )

    # Left-click opens the controls window
    icon = pystray.Icon(
        "AmpliFi Teleport",
        image,
        "AmpliFi Teleport Tray",
        menu=pystray.Menu(
            pystray.MenuItem("Open Controls", open_options_window, default=True, visible=False),
            *menu.items
        )
    )

    icon.run()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()