# MIDIWIN

Use Native Instruments Traktor Kontrol F1 and X1 MK1 controls for Windows media, volume, brightness and focused-window actions. The Tk console shows mappings and input activity. [MIDILIN](https://github.com/generalgroovy/midilin) is the Linux/Sway companion.

## Engineering overview

- **Input mapping:** configurable controller actions and modifier layers connect Traktor hardware to Windows desktop functions.
- **Windows integration:** device access, media and window actions, and display backends are coordinated through the Python runtime.
- **Operational visibility:** the Tk console provides mapping inspection, configuration validation and read-only monitoring; process ownership and a PID lock coordinate active control.

[Project overview](https://generalgroovy.web.app/apps/midilin-midiwin/) · [Python implementation](midiwin/) · [Tests](tests/)

## Install and open

Requires Windows and Python 3.11 or newer with Tcl/Tk. From a fresh checkout:

```powershell
git clone https://github.com/generalgroovy/midiwin.git
cd midiwin
Set-ExecutionPolicy -Scope Process Bypass -Force
.\setup.ps1 -NoStartup
.\launch-gui.cmd
```

Setup creates `.venv`, installs the application and development dependencies, and adds console shortcuts. `-NoStartup` omits the background login launcher. Run the same command after a normal `git pull --ff-only` to update while keeping your configuration.

Use `-ResetConfig` only when you want to replace your mappings with the shipped defaults. Setup first creates a timestamped configuration backup. Omit `-NoStartup` only when you want active control at login.

The F1 uses its HID driver. X1 raw USB access requires WinUSB; the separate `setup-x1-winusb.ps1` documents the guarded Zadig workflow. Ordinary setup and testing do not require changing drivers.

## Check and find controls

The console opens on **Mappings**, ready to explore without hardware. The setup strip shows the profile name, enabled mapping count and last device check. Its next-action button guides **Check saved profile → Detect devices → Monitor input**, with failures kept retryable. The full profile path is in **Display settings**.

Search by device, control, action, layer or state; filter Enabled/Disabled. **Clear filters** resets both the search and state filter and returns focus to search. No matches explains how to recover. Search does not edit the profile.

**Monitor & runtime** separates inspection (mapped actions off) from controls that apply mappings to your desktop. Its persistent process line stays separate from one-off diagnostic feedback. “Device check complete” means the command finished: review its list, then monitor actual input. It does not mean a controller was found or tested. Background state is not assumed at startup.

Select a row and choose **Inspect / try event** (or press Enter). The inspector shows readable field labels (**Show JSON** exposes exact configuration syntax), the complete mapping, referenced script/model definition where present, and an offline routing rehearsal. Choose an event and enter held controls such as `f1.shift`; **Try event** explains which mappings are eligible and why others are blocked. Multiple eligible mappings are shown in configuration order. Search also finds numeric parameters and profile fields; the table scrolls in both directions.

The inspector uses a snapshot of the loaded profile. Reopen it after reloading to inspect new configuration. It never opens controllers or runs mapped commands; it does not simulate action values, throttling, timing or hardware response. Windows tracks qualified `shift` / `hotcue` modifiers only; releases clear those modifiers before routing.

One-off diagnostics report their exit code, time out after 20 seconds, and put details in Monitor & runtime. Monitor startup service checks time out after 5 seconds. The log retains the latest 2,000 lines; restarting monitoring discards late output from the old child.

## First session

1. Open **Mappings** to inspect which controls perform which actions.
2. In **Monitor & runtime**, use **Detect devices**, then **Read-only monitor** or **Dry-run mappings** to inspect input and planned actions.
3. Use **Start active runtime** when ready to apply mappings. **Stop console process** ends the console-owned process. The runtime PID lock prevents two controller runtimes from running concurrently.
4. In **Display settings**, select the display and minimum brightness, then **Save configuration**. The brightness slider is a live test, not a preview.

Starting a monitor temporarily stops an existing background runtime. Stopping the monitor, or closing the console, resumes that runtime if it was previously active. Use `--stop-runtime` below when you intend to leave all control stopped.

## Configuration and recovery

Unsaved display changes are marked in the settings tab. Reload and close offer **Save / Discard / Cancel**; Cancel keeps both the draft and the current monitor. An invalid or failed save keeps the console open. Saving replaces a fully written profile atomically and preserves configuration fields outside the editor.


The default profile is `%APPDATA%\MidiWin\config.json`. On first launch without a profile, the shipped `config.default.json` is read without creating a file. **Save configuration** creates the profile. **Open config** explains when the profile needs its first save.

Copy the profile before editing it. Restore a chosen backup to `config.json` while the runtime is stopped, then validate and restart. Invalid JSON or mappings produce an error; a failed GUI reload keeps the last working configuration visible.

**Reload** refreshes the editable display fields as well as the mappings. Save rejects brightness minimums outside 0–100% without writing the profile, and the status confirms a successful save.

Choose a custom profile through the main entry point:

```powershell
.\.venv\Scripts\python.exe -m midiwin --gui --config C:\Profiles\midiwin.json
```

The same explicit profile is used for GUI loading, saving, monitoring and display commands. Relative paths are resolved before child processes start. An explicit missing file fails instead of silently using defaults. The `midiwin-gui` shortcut opens the default profile.

## Useful commands

Run from the checkout, using the installed environment:

```powershell
.\.venv\Scripts\python.exe -m midiwin --help
.\.venv\Scripts\python.exe -m midiwin --list-devices
.\.venv\Scripts\python.exe -m midiwin --validate-config
.\.venv\Scripts\python.exe -m midiwin --show-layout
.\.venv\Scripts\python.exe -m midiwin --runtime-status
.\.venv\Scripts\python.exe -m midiwin --stop-runtime
.\.venv\Scripts\python.exe -m midiwin --dry-run --set-brightness 50
```

Device detection works even if mappings need repair. `--monitor` and `--dry-run` inspect controller input without applying mapped desktop actions. Running without mode options starts active control. Display diagnostics use `--diagnose-display`; `--set-brightness 50` changes the display immediately unless paired with `--dry-run`.

Brightness first uses `screen-brightness-control`, including supported DDC/CI monitors, then Windows WMI for supported laptop panels. Available displays and permissions determine what can be controlled.

## Default controls

| Hardware | Examples |
| --- | --- |
| F1 Knob 1 / Knob 4 | Master volume / screen brightness |
| F1 Play 1–4 | Play/pause, previous, next, mute |
| F1 Reverse | Close the focused window |
| F1 Shift + Pads 1–4 | Configurable script/application slots |
| X1 Browse / Loop encoders | Move / resize the focused window |
| X1 FX2 Dry/Wet | Window opacity |
| X1 FX1 On / FX2 On | Maximize / restore |

Inspect **Mappings** or `--show-layout` for the active profile rather than assuming your saved controls match these defaults.

## Development and checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests cover configuration errors, GUI command routing, event mapping and display behavior using mocks; they do not certify a connected controller, driver installation or physical display response. [Source](midiwin/) · [Tests](tests/)

Build a standalone executable with `.\build-exe.ps1` after setup, or add `-BuildExe` to setup. Keep the complete `dist\MIDIWIN` folder together. Build output and installer changes require their own validation; a source test pass is not an installer acceptance result.

MIT license.
