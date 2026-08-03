# MIDIWIN — Traktor X1/F1 Windows System Controller

Windows-native sibling of [MIDILIN](https://github.com/generalgroovy/midilin).

MIDIWIN turns Native Instruments Traktor Kontrol F1 and X1 MK1 hardware into
Windows control surfaces for media, audio, display brightness, launchers,
scripts and focused-window movement, resizing and opacity.

## Controller console

The Tk GUI provides:

- a representative front-panel layout for F1 and X1;
- live highlighting of controls during read-only monitoring;
- mapping and modifier-layer overview;
- screen-brightness backend/display configuration and live testing;
- device detection, configuration validation and diagnostics;
- safe monitor/dry-run controls and active-runtime start/stop.

Launch after installation:

```powershell
.\launch-gui.cmd
```

The installer also creates **MIDIWIN Controller Console** shortcuts on the
Desktop and in the Start menu.

## Install or update

```powershell
git pull --ff-only
Set-ExecutionPolicy -Scope Process Bypass -Force
.\setup.ps1 -ResetConfig -NoStartup
```

`-ResetConfig` preserves the old configuration with a timestamped backup and
installs the new F1 Knob 4 brightness mapping. Remove `-NoStartup` to install the
background runtime at login.

Optional standalone executable build:

```powershell
.\setup.ps1 -ResetConfig -NoStartup -BuildExe
```

Result:

```text
dist\MIDIWIN\MIDIWIN.exe
```

## Display brightness

F1 Knob 4 maps to `brightness_absolute`. MIDIWIN first uses
`screen-brightness-control`, including supported DDC/CI displays, and then uses
Windows `WmiMonitorBrightnessMethods.WmiSetBrightness` as a laptop-panel
fallback. Configuration is stored under `display_controls.brightness`.

```powershell
.\.venv\Scripts\python.exe -m midiwin --diagnose-display
.\.venv\Scripts\python.exe -m midiwin --set-brightness 50
```

## Run and test

```powershell
.\.venv\Scripts\python.exe -m midiwin --list-devices
.\.venv\Scripts\python.exe -m midiwin --validate-config
.\.venv\Scripts\python.exe -m midiwin --show-layout
.\.venv\Scripts\python.exe -m midiwin --monitor
.\.venv\Scripts\python.exe -m midiwin --dry-run
.\.venv\Scripts\python.exe -m midiwin
.\.venv\Scripts\python.exe -m pytest -v
```

`--monitor` and `--dry-run` are read-only. MIDIWIN uses a PID lock to prevent two
processes from owning the controllers concurrently.

## Default controls

F1:

- Knob 1: master volume
- Knob 3: controller-light state
- Knob 4: screen brightness
- Play 1–4: play/pause, previous, next, mute
- Pad 1: browser
- Pad 2: Windows Terminal
- Reverse: close focused window
- Shift + Pads 1–4: Codex, Ollama, Odysseus and custom script slots

X1:

- Browse encoders: move focused window horizontally and vertically
- Loop encoders: resize width and height
- FX2 Dry/Wet: window opacity
- FX1 On: maximize
- FX2 On: restore

## X1 driver

X1 raw USB access requires WinUSB. Run `setup-x1-winusb.ps1` for the guarded
Zadig workflow. The F1 remains on its HID driver.

## Configuration

```text
%APPDATA%\MidiWin\config.json
```

## Related project

- Windows: **MIDIWIN** — this repository
- Linux/Sway: **[MIDILIN](https://github.com/generalgroovy/midilin)**

## License

MIT
