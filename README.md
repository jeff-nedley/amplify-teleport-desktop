# AmpliFi Teleport for Desktop

**Unofficial desktop client for AmpliFi Teleport**

## Disclaimer
This is an **unofficial** tool — not affiliated with, endorsed by, or supported by Ubiquiti Inc. or AmpliFi. Use at your own risk.

## Overview

Generate WireGuard VPN configurations for AmpliFi routers with Teleport enabled — so you can securely access your home network from anywhere.

This project started as a fork of an earlier community tool and has been completely rewritten with a modern, user-friendly interface, system tray / menu bar integration, automatic reconnection support, and a clean GUI that feels native on both **Windows** and **macOS**.

**Why this exists**  
Ubiquiti has not yet released an official desktop client for AmpliFi Teleport — only mobile apps are available. This tool fills that gap.

## Features

- System tray (Windows) / menu bar (macOS) icon for quick access
- One-time PIN entry (stored securely in the OS app-data location)
- Automatic tunnel activation on connect (if previously configured)
- Refresh existing configuration without re-entering PIN
- Delete & reset configuration option to re-enter PIN
- Modern UI built with CustomTkinter — same layout and branding on both platforms, with native fonts and window/icon behavior
- Desktop notifications for status & errors (Windows toast / macOS Notification Center)
- Identical Connect / Disconnect / Delete / Quit behavior on Windows and macOS

## Requirements

### Both platforms
- [WireGuard](https://www.wireguard.com/install/) tooling installed (see below)
- An active AmpliFi router with Teleport enabled
- A valid Teleport PIN from the AmpliFi mobile app
- Python 3.10+ (when running from source)

### Windows
- Windows 10 or 11 (64-bit)
- Official [WireGuard for Windows](https://www.wireguard.com/install/) client (bundled by the installer)

### macOS
- macOS 12+ (Intel or Apple Silicon)
- Homebrew WireGuard tools (and bash 4+ for `wg-quick`):

```bash
brew install wireguard-tools bash
```

## Installation

### Windows
1. Go to the **[Releases page](https://github.com/jeff-nedley/amplify-teleport-desktop/releases)**  
2. Download the latest **.exe installer** (e.g. `AmpliFi Teleport For Desktop Setup.exe`)  
3. Run the installer and follow the prompts  
4. The control window appears; when closed with **X**, the app stays in the system tray (hidden icons area ↑)

### macOS (from source)
```bash
git clone https://github.com/jeff-nedley/amplify-teleport-desktop.git
cd amplify-teleport-desktop
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Optional: build a `.app` bundle with `./build_macos.sh` (requires PyInstaller).

## How to Use

1. **Open the controls**  
   - **Windows:** left-click the tray icon (blue Wi-Fi symbol)  
   - **macOS:** click the menu bar icon → **Open Controls**

2. **First time only**  
   Click **Connect** → enter your Teleport PIN from the AmpliFi mobile app  
   → Tunnel connects automatically  
   - **Windows:** the app requests Administrator rights at startup (required for the WireGuard tunnel service)  
   - **macOS:** macOS may prompt for an administrator password when bringing the tunnel up or down

3. **Subsequent use**  
   - Click **Connect** to activate the tunnel  
   - Click **Disconnect** to deactivate  
   - Click **Delete Existing Configuration** to reset and force a new PIN entry

4. **Quit**  
   Click **Quit** in the control window (or the tray / menu bar menu) → fully exits the application

## Data locations

| OS | Config / token / log directory |
| --- | --- |
| Windows | `%APPDATA%\AmpliFiTeleport\` |
| macOS | `~/Library/Application Support/AmpliFiTeleport/` |

## Building from Source (Developers)

```bash
# Clone repo
git clone https://github.com/jeff-nedley/amplify-teleport-desktop.git
cd amplify-teleport-desktop

# Install dependencies
python3 -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt

# Run
python main.py
```

### Package

- **Windows:** `.\build_exe.ps1` then compile `app_installer_script.iss` with Inno Setup  
- **macOS:** `./build_macos.sh` → `dist/AmpliFi Teleport for Desktop.app`
