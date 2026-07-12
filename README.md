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
- Identical professional UI on Windows and macOS (PySide6 / Qt), with AmpliFi branding
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
  - **Windows:** `Amplifi Teleport For Desktop Setup-<version>.exe`
  - **macOS:** `Amplifi Teleport For Desktop Setup-<version>.dmg` (open it, then run the `.pkg` inside)
2. Follow the installer prompts (administrator permission required)
3. If WireGuard is not already installed, Setup installs it silently
4. The app launches when installation finishes

**Uninstall:** use Apps & features on Windows, or **Uninstall AmpliFi Teleport** in Applications on macOS (Spotlight-searchable app). You will be asked whether to remove WireGuard as well.

## How to Use

### Windows

1. Left-click the tray icon (blue Wi-Fi symbol) to open controls — if the window was closed, look in the hidden icons area (↑)
2. **First time:** click **Connect**, enter your 5-character Teleport PIN, and wait for the tunnel to connect
3. Later: use **Connect**, **Disconnect**, or **Delete saved configuration** to reset and enter a new PIN
4. Click **Quit AmpliFi Teleport** to fully exit (also disconnects the tunnel if it is still connected)

The app requests Administrator rights at startup (required for the WireGuard tunnel service).

### macOS

1. Look in the **menu bar** (top-right, near the clock) for the AmpliFi Teleport icon — there is no Dock icon while the window is hidden
  - On notched MacBooks the icon may be inside the menu bar overflow (click the icon next to Control Center)
2. Click it → **Open Controls** (closing the window hides it; the app stays running in the menu bar)
3. **First time:** click **Connect**, enter your 5-character Teleport PIN, and wait for the tunnel to connect
4. Later: use **Connect**, **Disconnect**, or **Delete saved configuration** to reset and enter a new PIN
5. Click **Quit** (menu bar or **Quit AmpliFi Teleport** in the control window) to fully exit — this also disconnects the tunnel if it is still connected

macOS may prompt for an administrator password **once** (at Setup install, or the first time you run from source). After that, Connect / Disconnect should not ask again.

## Data location


|         | Path                                             |
| ------- | ------------------------------------------------ |
| Windows | `%APPDATA%\AmpliFiTeleport\`                     |
| macOS   | `~/Library/Application Support/AmpliFiTeleport/` |


## Developing from source

### 1. Prepare the environment

```bash
git clone https://github.com/jeff-nedley/amplify-teleport-desktop.git
cd amplify-teleport-desktop
python3 -m venv .venv
source .venv/bin/activate        # Windows (PowerShell): .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS extras** (needed for Connect / Disconnect from source, and for the menu bar helper):

```bash
brew install wireguard-tools bash
# Cocoa bindings are already pulled in by requirements.txt on Darwin
```

**Windows extras:** install [WireGuard for Windows](https://www.wireguard.com/install/) so `wireguard.exe` is available, and run the app elevated when testing tunnels.

### 2. Run the app

```bash
python main.py
```

On macOS, look for the menu bar icon. On Windows, look for the tray icon (and approve the UAC prompt if shown).

### 3. Run the tests

The suite covers platform helpers, installer parity, mocked tunnel connect/disconnect/delete, and Qt UI flows (no live Teleport PIN / AmpliFi API required):

```bash
./run_tests.sh
# or:
QT_QPA_PLATFORM=offscreen python3 -m unittest \
  test_platform test_installer_parity test_tunnel_functional test_ui_functional -v
```

On Windows (PowerShell), from an activated venv:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest test_platform test_installer_parity test_tunnel_functional test_ui_functional -v
```

### 4. Build releases

Release version is read from the root `VERSION` file (and synced into `version.iss` for Inno Setup).

Release entry points run the full unit test suite **before** packaging and abort if anything fails.

```bash
# On a Mac — Setup DMG
./build_release.sh --macos

# On Windows — Setup exe (PyInstaller + Inno Setup 6)
.\build_release.ps1 -Windows

# Build whatever this machine can produce
./build_release.sh --all

# Optional: bump VERSION first, then build
./build_release.sh --version=2.0.0 --macos
```

Outputs land in `dist/`:

- macOS: `Amplifi Teleport For Desktop Setup-<version>.dmg`
- Windows: `Amplifi Teleport For Desktop Setup-<version>.exe`

A full dual-OS GitHub release still needs one pass on each OS (or CI runners for both).

Lower-level builders (also gate on unit tests unless you pass `--skip-tests` / `-SkipTests`):

```bash
./build_macos_dmg.sh          # macOS DMG only
.\build_exe.ps1               # Windows app + installer only
```

Emergency escape hatch (not recommended for real releases):

```bash
./build_release.sh --macos --skip-tests
.\build_release.ps1 -Windows -SkipTests
```

