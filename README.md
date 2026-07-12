# AmpliFi Teleport for Desktop

**Unofficial desktop client for AmpliFi Teleport**

> Not affiliated with, endorsed by, or supported by Ubiquiti Inc. or AmpliFi. Use at your own risk.

Generate WireGuard VPN configs for AmpliFi routers with Teleport enabled, so you can securely reach your home network from anywhere. Ubiquiti only ships mobile apps today; this fills the desktop gap.

**Releases:** [github.com/jeff-nedley/amplify-teleport-desktop/releases](https://github.com/jeff-nedley/amplify-teleport-desktop/releases)

## Features

- Connect, disconnect, and manage your Teleport tunnel from a simple control window
- One-time Teleport PIN entry (stored securely in the app data folder)
- Reconnect without re-entering the PIN
- System tray (Windows) / menu bar status item (macOS, no Dock icon)
- Identical dark UI on Windows and macOS (PySide6 / Qt)
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
1. Look in the **menu bar** (top-right, near the clock) for the AmpliFi Teleport icon — there is no Dock icon while the window is hidden
   - On notched MacBooks the icon may be inside the menu bar overflow (click the icon next to Control Center)
2. Click it → **Open Controls** (closing the window hides it; the app stays running in the menu bar)
3. **First time:** click **Connect**, enter your 5-character Teleport PIN, and wait for the tunnel to connect
4. Later: use **Connect**, **Disconnect**, or **Delete Existing Configuration** to reset and enter a new PIN
5. Click **Quit** (menu bar or control window) to fully exit the application

macOS may prompt for an administrator password **once** (at Setup install, or the first time you run from source). After that, Connect / Disconnect should not ask again.

When running from source, Dock and Notification Center may show the Python icon (macOS attributes those to the delivering process). The DMG-installed `.app` shows the AmpliFi Teleport icon.

From source on macOS, make sure Cocoa bindings are installed:

```bash
pip install 'pyobjc-framework-Cocoa>=10.0'
```

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

On macOS, install WireGuard tools first if you are not using the Setup DMG:

```bash
brew install wireguard-tools bash
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
