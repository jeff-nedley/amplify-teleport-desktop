# AmpliFi Teleport for Desktop

**Unofficial desktop client for AmpliFi Teleport**

> Not affiliated with, endorsed by, or supported by Ubiquiti Inc. or AmpliFi. Use at your own risk.

Generate WireGuard VPN configs for AmpliFi routers with Teleport enabled, so you can securely reach your home network from anywhere. Ubiquiti only ships mobile apps today; this fills the desktop gap.

**Releases:** [github.com/jeff-nedley/amplify-teleport-desktop/releases](https://github.com/jeff-nedley/amplify-teleport-desktop/releases)

## Features

- Connect, disconnect, and manage your Teleport tunnel from a simple control window
- One-time Teleport PIN entry (stored securely in the app data folder)
- Reconnect without re-entering the PIN
- System tray / menu bar icon for quick access
- Desktop notifications for status and errors
- Installer automatically installs WireGuard when it is missing

## Requirements

### Windows
- Windows 10 or 11 (64-bit)
- AmpliFi router with Teleport enabled
- Teleport PIN from the AmpliFi mobile app
- [WireGuard for Windows](https://www.wireguard.com/install/) — installed automatically by Setup if missing

### macOS
- macOS 12+ (Intel or Apple Silicon)
- AmpliFi router with Teleport enabled
- Teleport PIN from the AmpliFi mobile app
- WireGuard CLI tools (`wg` / `wg-quick`) — installed automatically by Setup if missing

## Installation

1. Download the latest release from the [Releases page](https://github.com/jeff-nedley/amplify-teleport-desktop/releases)
   - **Windows:** `Amplifi.Teleport.For.Desktop.Setup-1.0.0.exe`
   - **macOS:** `Amplifi Teleport For Desktop Setup-1.0.0.dmg` (open it, then run the `.pkg` inside)
2. Follow the installer prompts (administrator permission required)
3. If WireGuard is not already installed, Setup installs it silently
4. The app launches when installation finishes

**Uninstall:** use system uninstall on Windows, or **Uninstall AmpliFi Teleport** in Applications on macOS. You will be asked whether to remove WireGuard as well.

## How to Use

### Windows
1. Left-click the tray icon (blue Wi-Fi symbol) to open controls — if the window was closed, look in the hidden icons area (↑)
2. **First time:** click **Connect**, enter your 5-character Teleport PIN, and wait for the tunnel to connect
3. Later: use **Connect**, **Disconnect**, or **Delete Existing Configuration** to reset and enter a new PIN
4. Click **Quit** to fully exit the application

The app requests Administrator rights at startup (required for the WireGuard tunnel service).

### macOS
1. Click the menu bar icon → **Open Controls**
2. **First time:** click **Connect**, enter your 5-character Teleport PIN, and wait for the tunnel to connect
3. Later: use **Connect**, **Disconnect**, or **Delete Existing Configuration** to reset and enter a new PIN
4. Click **Quit** to fully exit the application

macOS may prompt for an administrator password when bringing the tunnel up or down.

## Data location

| | Path |
| --- | --- |
| Windows | `%APPDATA%\AmpliFiTeleport\` |
| macOS | `~/Library/Application Support/AmpliFiTeleport/` |

## Building from source

```bash
git clone https://github.com/jeff-nedley/amplify-teleport-desktop.git
cd amplify-teleport-desktop
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### Packaging

```powershell
# Windows — then compile app_installer_script.iss with Inno Setup
.\build_exe.ps1
```

```bash
# macOS — produces the Setup DMG (includes WireGuard auto-install)
./build_macos_dmg.sh
```
