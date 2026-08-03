# MIDIWIN — Traktor X1/F1 Windows System Controller

Windows-native sibling of [MIDILIN](https://github.com/generalgroovy/midilin).

Use Native Instruments Traktor Kontrol F1 and X1 MK1 hardware as complementary
Windows control surfaces for media, audio, applications, scripts, focused-window
movement and sizing, monitor transfer, diagnostics, local-model parameters and
interactive LEDs.

- **F1:** desktop launchers, media, audio, display controls, workspaces through
  Windows virtual desktops, model controls and sixteen Shift script slots.
- **X1:** focused-window placement, movement, resizing, opacity, monitor transfer,
  snap presets, diagnostics and eight Shift script slots.

The Linux implementation lives in
[`generalgroovy/midilin`](https://github.com/generalgroovy/midilin).

## Status

This repository contains a usable Windows foundation:

- F1 HID input and RGB output through `hidapi`;
- X1 MK1 raw USB input and LED output through `PyUSB`/WinUSB;
- Win32 foreground-window close, move, resize, opacity, maximize, restore and
  monitor-transfer actions;
- media keys and absolute endpoint volume control;
- configurable PowerShell, executable and Python script slots;
- connection consent with remembered per-device decisions;
- persistent LED brightness and visual themes;
- monitor mode, dry-run mode, configuration validation and layout display;
- PowerShell setup, autostart and uninstall scripts;
- unit tests and GitHub Actions validation.

## Hardware driver note

The F1 normally exposes a HID interface directly. X1 MK1 raw USB access may
require assigning its interface to **WinUSB** with Zadig. Replacing the Native
Instruments driver can prevent Traktor from using the same device until the
original driver is restored. The installer never changes USB drivers
silently.

## Install

Open PowerShell in the repository:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
```

The setup script creates `.venv`, installs dependencies, copies the default
configuration to `%APPDATA%\MidiWin`, and optionally creates a Startup shortcut.

Run manually:

```powershell
.\.venv\Scripts\python.exe -m midiwin --list-devices
.\.venv\Scripts\python.exe -m midiwin --validate-config
.\.venv\Scripts\python.exe -m midiwin --show-layout
.\.venv\Scripts\python.exe -m midiwin
```

Test physical controls without running system actions:

```powershell
.\.venv\Scripts\python.exe -m midiwin --dry-run
```

## Default configuration

```text
%APPDATA%\MidiWin\config.json
%APPDATA%\MidiWin\defaults\actions.json
%APPDATA%\MidiWin\defaults\f1.json
%APPDATA%\MidiWin\defaults\x1.json
%APPDATA%\MidiWin\defaults\scripts.json
%APPDATA%\MidiWin\defaults\model.json
%APPDATA%\MidiWin\defaults\visuals.json
```

Configuration concepts intentionally mirror MIDILIN so mappings and script-slot
ideas can be transferred between operating systems while action implementations
remain platform-native.

## Documentation

- [`docs/LAYOUT.md`](docs/LAYOUT.md)
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)
- [`docs/DRIVERS.md`](docs/DRIVERS.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Related project

- Windows: **MIDIWIN** — this repository
- Linux/Sway: **[MIDILIN](https://github.com/generalgroovy/midilin)**

## License

MIT
