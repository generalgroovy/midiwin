# MIDIWIN — Traktor X1/F1 Windows System Controller

Windows-native sibling of [MIDILIN](https://github.com/generalgroovy/midilin).

MIDIWIN turns Native Instruments Traktor Kontrol F1 and X1 MK1 hardware into
Windows control surfaces for media, audio, launchers, scripts and focused-window
movement, resizing and opacity.

## Current baseline

Implemented:

- F1 HID discovery and input through `hidapi`;
- X1 MK1 raw USB discovery and input through `PyUSB`/WinUSB;
- F1 buttons, pads, encoder, knobs and faders;
- X1 buttons, four encoders and eight analog knobs;
- media play/pause, previous, next and mute;
- endpoint volume through `pycaw`;
- focused-window close, move, resize, opacity, maximize and restore;
- browser, Windows Terminal and configurable script slots;
- Shift layers, monitor mode, dry-run mode, configuration validation and layout
  display;
- PowerShell installation and optional Startup shortcut;
- Windows GitHub Actions validation and unit tests.

Planned next: F1 RGB output, X1 LED output, graphical connection consent,
monitor-transfer presets, virtual-desktop integration and richer visual themes.

## Hardware driver note

The F1 normally exposes a HID interface directly. X1 MK1 raw USB access may
require assigning its interface to **WinUSB** with Zadig. Replacing the Native
Instruments driver can prevent Traktor from using the same device until the
original driver is restored. `setup.ps1` never changes USB drivers.

## Install

Clone or pull the repository, then open PowerShell inside it:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
```

The setup script creates `.venv`, installs the package and test dependencies,
copies `config.default.json` to `%APPDATA%\MidiWin\config.json`, optionally
creates a Startup shortcut, validates the configuration and runs the tests.

Install without autostart:

```powershell
.\setup.ps1 -NoStartup
```

Replace the active configuration while preserving a timestamped backup:

```powershell
.\setup.ps1 -ResetConfig
```

## Run and test

```powershell
# Detect supported hardware
.\.venv\Scripts\python.exe -m midiwin --list-devices

# Validate JSON mappings
.\.venv\Scripts\python.exe -m midiwin --validate-config

# Print the active layout
.\.venv\Scripts\python.exe -m midiwin --show-layout

# Display raw controller events only
.\.venv\Scripts\python.exe -m midiwin --monitor

# Route mappings but do not execute Windows actions
.\.venv\Scripts\python.exe -m midiwin --dry-run

# Run normally
.\.venv\Scripts\python.exe -m midiwin

# Run automated tests
.\.venv\Scripts\python.exe -m pytest -v
```

Stop monitor, dry-run or normal mode with `Ctrl+C`.

## Default controls

F1:

- Knob 1: master volume
- Knob 3: controller-light state value
- Play 1–4: play/pause, previous, next, mute
- Pad 1: browser
- Pad 2: Windows Terminal
- Reverse: close focused window
- Shift + Pads 1–4: Codex, Ollama, Odysseus and custom script slots

X1:

- Browse encoders: move focused window horizontally and vertically
- Loop encoders: resize focused window width and height
- FX2 Dry/Wet: focused-window opacity
- FX1 On: maximize
- FX2 On: restore

## Configuration

```text
%APPDATA%\MidiWin\config.json
```

The repository default is [`config.default.json`](config.default.json).
Configuration concepts mirror MIDILIN where practical, while actions remain
platform-native.

## Related project

- Windows: **MIDIWIN** — this repository
- Linux/Sway: **[MIDILIN](https://github.com/generalgroovy/midilin)**

## License

MIT
