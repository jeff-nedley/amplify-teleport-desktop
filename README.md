# AmpliFi Teleport for Desktop

**Unofficial desktop client for AmpliFi Teleport**

Generate WireGuard VPN configurations for AmpliFi routers with Teleport enabled — so you can securely access your home network from anywhere.

This project started as a fork of an earlier community tool and has been completely rewritten with a modern, user-friendly interface, system tray integration, automatic reconnection support, and a clean GUI.

**Why this exists**  
Ubiquiti has not yet released an official desktop client for AmpliFi Teleport — only mobile apps are available. This tool fills that gap.

## Features

- System tray icon to quickly access menu
- One-time PIN entry (stored securely in %APPDATA%)
- Automatic tunnel activation on startup (if previously configured)
- Refresh existing configuration without re-entering PIN
- Delete & reset configuration option to re-enter PIN
- Modern UI built with CustomTkinter
- Windows toast notifications for status & errors
- Runs silently in background (no console window)

## Requirements

- Windows 10 or 11 (64-bit)
- [WireGuard official client](https://www.wireguard.com/install/) installed (Gets bundled with installer)
- An active AmpliFi router with Teleport enabled
- A valid Teleport PIN from the AmpliFi mobile app

## Installation

1. Go to the **[Releases page](https://github.com/JeffNedley/amplify-teleport-desktop/releases)**  
2. Download the latest **.exe installer** (e.g. `AmpliFi Teleport For Desktop Setup.exe`)  
3. Run the installer and follow the prompts  
4. The application menu will appear and stay in your system tray (hidden icons area ↑) when the menu is closed with the X

## How to Use

1. **Locate the tray icon**  
   Click the hidden icons arrow (↑) in the bottom-right taskbar

2. **Left-click** the AmpliFi Teleport icon (blue Wi-Fi symbol)  
   → Opens the control window

3. **First time only**  
   Click **Connect** → enter your Teleport PIN from the AmpliFi mobile app  
   → Tunnel connects automatically

4. **Subsequent use**  
   - Click **Connect** to activate the tunnel  
   - Click **Disconnect** to deactivate  
   - Click **Delete Existing Configuration** to reset and force a new PIN entry

5. **Quit**  
   Click **Quit** in the control window → fully exits the application

## Building from Source (Developers)

```bash
# Clone repo
git clone https://github.com/JeffNedley/amplify-teleport-desktop.git
cd amplify-teleport-desktop

# Install dependencies
pip install -r requirements.txt

# Run
python main.py