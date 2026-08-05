# MIDIWIN Autocode integration

MIDIWIN can control Autocode running on the Linux workstation through Windows
OpenSSH. The transport is encrypted, non-interactive, and restricted to a fixed
action enum. It does not expose a plaintext HTTP token, PowerShell command,
configurable remote command, or general remote shell field.

## Current capabilities

- shifted F1 and Hotcue-layer X1 Autocode actions;
- encrypted SSH execution with `BatchMode=yes`;
- bounded connection and command timeouts;
- periodic read-only Autocode state polling;
- structured MIDIWIN event logging;
- optional Windows system audio cue when a completion is pending;
- CLI state/action diagnostics.

MIDIWIN does not currently implement F1/X1 output LED transport. Its JSON status
reports `controller_led_feedback: false`. Use MIDILIN on Linux for physical LED
state feedback.

## Linux prerequisites

Autocode must be installed and the fixed MIDI bridge must work locally:

```fish
autocode-local midi-state ~/Projects/flux2
autocode-local midi-action status ~/Projects/flux2
```

The Linux SSH server must accept key authentication for the same user that owns
the Autocode state and processes.

## Windows OpenSSH setup

Verify the client:

```powershell
ssh.exe -V
```

Create a dedicated key when required:

```powershell
ssh-keygen.exe -t ed25519 -f "$env:USERPROFILE\.ssh\autocode_midicontroller"
```

Install the public key in the Linux user’s `~/.ssh/authorized_keys`, then add a
host entry to `%USERPROFILE%\.ssh\config`:

```text
Host opitop-autocode
    HostName opitop
    User otp
    IdentityFile ~/.ssh/autocode_midicontroller
    IdentitiesOnly yes
```

Confirm that no password or host-key prompt appears:

```powershell
ssh.exe -T -o BatchMode=yes opitop-autocode autocode-local midi-action status /home/otp/Projects/flux2
```

MIDIWIN deliberately fails when key authentication is unavailable instead of
opening a password prompt from the controller runtime.

## MIDIWIN configuration

Edit:

```text
%APPDATA%\MidiWin\config.json
```

Enable the integration and select the Linux workspace:

```json
{
  "autocode": {
    "enabled": true,
    "transport": "ssh",
    "ssh_binary": "ssh.exe",
    "ssh_host": "opitop-autocode",
    "remote_binary": "autocode-local",
    "workspace": "/home/otp/Projects/flux2",
    "connect_timeout_seconds": 5,
    "poll_seconds": 1.0,
    "audio_cue": true
  }
}
```

Constraints:

- transport must be `ssh`;
- SSH and remote executable values must be simple executable/host tokens;
- workspace must be an absolute POSIX path without spaces, traversal, or shell
  metacharacters;
- connection timeout: 1–30 seconds;
- poll interval: 0.25–30 seconds.

Validate:

```powershell
python -m midiwin --validate-config
python -m midiwin --json-status
python -m midiwin --autocode-state
```

## Fixed transport

MIDIWIN constructs this argument vector:

```text
ssh.exe
-T
-o BatchMode=yes
-o ConnectTimeout=5
-o ServerAliveInterval=5
-o ServerAliveCountMax=1
-o RequestTTY=no
--
<host>
autocode-local
midi-action
<ACTION>
<workspace>
```

Allowed actions:

```text
status
open
pause
resume
stop
cancel
overnight-stop
morning
acknowledge
cue-test
```

Unknown actions and unsafe configuration fields are rejected before SSH starts.

Manual operations:

```powershell
python -m midiwin --autocode-action status
python -m midiwin --autocode-action cue-test
python -m midiwin --autocode-action acknowledge
```

## F1 shifted layout

Hold F1 SHIFT:

| Control | Action |
|---|---|
| Grid 5 | Open Control Center |
| Grid 6 | Status |
| Grid 7 | Pause |
| Grid 8 | Resume |
| Grid 9 | Stop |
| Grid 10 | Cancel |
| Grid 11 | Stop overnight queue |
| Grid 12 | Acknowledge pending completion |
| Grid 13 | Locate morning report |
| Grid 14 | Cue test |

Existing non-shifted and earlier shifted mappings remain unchanged.

## X1 Hotcue layer

Hold X1 HOTCUE:

| Control | Action |
|---|---|
| Deck A IN | Open Control Center |
| Deck A OUT | Status |
| Deck A beat left | Pause |
| Deck A beat right | Resume |
| Deck A CUE | Stop |
| Deck A CUP | Cancel |
| Deck A PLAY | Stop overnight queue |
| Deck A SYNC | Acknowledge pending completion |
| Deck B IN | Locate morning report |
| Deck B OUT | Cue test |

## Completion polling and sound

The runtime polls the normalized Autocode state through the fixed `status`
action. It processes a state only when the sequence number changes. When
`cue_pending=true` and the state is `attention`, `completed`, or `failed`,
MIDIWIN can play a fixed Windows `winsound.MessageBeep` cue.

The watcher does not acknowledge automatically. Press the configured acknowledge
control so the completion remains visible to MIDILIN, MIDIWIN, and the user until
explicitly cleared.

Disable Windows sound while retaining state polling:

```json
{
  "autocode": {
    "audio_cue": false
  }
}
```

## Diagnostics

```powershell
python -m midiwin --json-status
python -m midiwin --event-tail 100
python -m midiwin --monitor
```

The JSON status includes:

- enabled state;
- SSH transport, host, and workspace;
- latest normalized Autocode state or connection error;
- fixed actions;
- `arbitrary_commands: false`;
- `controller_led_feedback: false`;
- Windows audio feedback setting.

## Validation

```powershell
cd C:\Users\sende\Projects\midiwin
git fetch origin
git switch agent/observable-runtime-20260804
git pull --ff-only
.\setup.ps1
python -m midiwin --validate-config --config config.default.json
python -m unittest discover -s tests -v
python -m midiwin --json-status
.\build-exe.ps1
```

Physical/runtime validation still required:

- Windows-to-Linux key-only SSH;
- actual F1 and X1 button combinations;
- completion polling over the real network;
- Windows audio cue;
- runtime reconnect behavior after Linux suspend/restart;
- no password dialog during controller operation.

Automated Windows CI cannot prove real controller input or connectivity to
`opitop`.
