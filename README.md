# AmpliFi Teleport for Desktop

**Unofficial desktop client for AmpliFi Teleport** — Windows & macOS

> Not affiliated with, endorsed by, or supported by Ubiquiti Inc. or AmpliFi. Use at your own risk.

Generate WireGuard VPN configs for AmpliFi routers with Teleport enabled, so you can securely reach your home network from anywhere. Ubiquiti only ships mobile apps today; this fills the desktop gap.

**Releases:** [github.com/jeff-nedley/amplify-teleport-desktop/releases](https://github.com/jeff-nedley/amplify-teleport-desktop/releases)

---

## Features

- Connect / Disconnect / Delete config / Quit — same on both OSes
- One-time Teleport PIN (stored in the OS app-data folder)
- Reconnect without re-entering the PIN
- System tray (Windows) / menu bar (macOS)
- Desktop notifications for status and errors
- Installer auto-installs WireGuard when missing

---

## Windows

### Requirements
- Windows 10 or 11 (64-bit)
- AmpliFi router with Teleport enabled + PIN from the AmpliFi mobile app
- [WireGuard for Windows](https://www.wireguard.com/install/) — installed automatically by Setup if missing

### Install
1. Download the latest **Setup `.exe`** from [Releases](https://github.com/jeff-nedley/amplify-teleport-desktop/releases)
2. Run the installer and follow the prompts (administrator / UAC)
3. If WireGuard is missing, Setup downloads and installs it silently
4. The control window opens; closing it with **X** leaves the app in the system tray (hidden icons ↑)

### Use
1. Left-click the tray icon (blue Wi-Fi) to open controls
2. **First time:** **Connect** → enter your 5-character Teleport PIN → tunnel connects
3. Later: **Connect** / **Disconnect**, or **Delete Existing Configuration** to reset the PIN
4. **Quit** from the control window or tray menu to fully exit

The app requests Administrator rights at startup (required for the WireGuard tunnel service).

### Uninstall
Use **Apps & features** / Settings → uninstall **AmpliFi Teleport for Desktop**.  
You will be asked whether to remove WireGuard as well.

### Data
`%APPDATA%\AmpliFiTeleport\`

### Build (developers)
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python main.py

# Package installer
.\build_exe.ps1
# Then compile app_installer_script.iss with Inno Setup
# → Amplifi Teleport For Desktop Setup-<version>.exe
```

---

## macOS

### Requirements
- macOS 12+ (Intel or Apple Silicon)
- AmpliFi router with Teleport enabled + PIN from the AmpliFi mobile app
- WireGuard CLI (`wg` / `wg-quick`) — installed automatically by Setup if missing

### Install
1. Download the latest **Setup `.dmg`** from [Releases](https://github.com/jeff-nedley/amplify-teleport-desktop/releases)
2. Open the DMG and double-click the **Setup `.pkg`**
3. Follow the installer (administrator password required)
4. If WireGuard is missing, Setup installs it silently via Homebrew (`wireguard-tools` + `bash`)
5. The app launches when setup finishes; use the menu bar icon after closing the window

### Use
1. Click the menu bar icon → **Open Controls**
2. **First time:** **Connect** → enter your 5-character Teleport PIN → tunnel connects
3. Later: **Connect** / **Disconnect**, or **Delete Existing Configuration** to reset the PIN
4. **Quit** from the control window or menu bar menu to fully exit

macOS may prompt for an administrator password when bringing the tunnel up or down.

### Uninstall
Open **Uninstall AmpliFi Teleport** from Applications.  
You will be asked whether to remove WireGuard as well.

### Data
`~/Library/Application Support/AmpliFiTeleport/`

### Build (developers)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py

# Package installer DMG (app + WireGuard auto-install)
./build_macos_dmg.sh
# → dist/Amplifi Teleport For Desktop Setup-<version>.dmg
```

---

## Installer parity

| Step | Windows | macOS |
| --- | --- | --- |
| Distribute | Setup `.exe` | Setup `.dmg` → `.pkg` |
| App location | Program Files | `/Applications` |
| Detect WireGuard | Registry / `wg.exe` | `wg` + `wg-quick` |
| If missing | Silent MSI (`msiexec /qn`) | Silent Homebrew (`wireguard-tools` + `bash`) |
| Launch after setup | Yes | Yes |
| Uninstall can remove WireGuard | Yes | Yes |
