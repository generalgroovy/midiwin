from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
from typing import Any, Callable

from .eventlog import emit


AUTOCODE_ACTIONS = {
    "status",
    "open",
    "pause",
    "resume",
    "stop",
    "cancel",
    "overnight-stop",
    "morning",
    "acknowledge",
    "cue-test",
}
AUTOCODE_STATES = {
    "idle",
    "starting",
    "running",
    "paused",
    "attention",
    "completed",
    "failed",
    "stopped",
}
_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,254}$")
_BINARY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_WORKSPACE = re.compile(r"^/[A-Za-z0-9._/-]+$")
MAX_RESPONSE_BYTES = 64 * 1024


def settings(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("autocode", {})
    return raw if isinstance(raw, dict) else {}


def enabled(config: dict[str, Any]) -> bool:
    return bool(settings(config).get("enabled", False))


def validate(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    raw = config.get("autocode", {})
    if not isinstance(raw, dict):
        return ["autocode must be an object"]
    transport = str(raw.get("transport", "ssh"))
    if transport != "ssh":
        errors.append("autocode.transport must be ssh")
    host = str(raw.get("ssh_host", "otp@opitop")).strip()
    if not _HOST.fullmatch(host) or host.startswith("-"):
        errors.append("autocode.ssh_host contains unsupported characters")
    ssh_binary = str(raw.get("ssh_binary", "ssh.exe")).strip()
    if not _BINARY.fullmatch(ssh_binary):
        errors.append("autocode.ssh_binary must be a simple executable name")
    remote_binary = str(raw.get("remote_binary", "autocode-local")).strip()
    if not _BINARY.fullmatch(remote_binary):
        errors.append("autocode.remote_binary must be a simple executable name")
    workspace = str(raw.get("workspace", "/home/otp/Projects/flux2")).strip()
    if (
        not _WORKSPACE.fullmatch(workspace)
        or "//" in workspace
        or ".." in workspace.split("/")
    ):
        errors.append(
            "autocode.workspace must be an absolute POSIX path without spaces or traversal"
        )
    connect_timeout = int(raw.get("connect_timeout_seconds", 5))
    if connect_timeout < 1 or connect_timeout > 30:
        errors.append("autocode.connect_timeout_seconds must be between 1 and 30")
    poll = float(raw.get("poll_seconds", 1.0))
    if poll < 0.25 or poll > 30:
        errors.append("autocode.poll_seconds must be between 0.25 and 30")
    return errors


def _validated(config: dict[str, Any]) -> dict[str, Any]:
    errors = validate(config)
    if errors:
        raise ValueError("; ".join(errors))
    return settings(config)


def ssh_command(config: dict[str, Any], action: str) -> list[str]:
    if action not in AUTOCODE_ACTIONS:
        raise ValueError(f"unsupported Autocode action: {action}")
    value = _validated(config)
    ssh_name = str(value.get("ssh_binary", "ssh.exe"))
    ssh = shutil.which(ssh_name)
    if not ssh:
        raise FileNotFoundError(f"OpenSSH client not found: {ssh_name}")
    timeout = int(value.get("connect_timeout_seconds", 5))
    return [
        ssh,
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={timeout}",
        "-o",
        "ServerAliveInterval=5",
        "-o",
        "ServerAliveCountMax=1",
        "-o",
        "RequestTTY=no",
        "--",
        str(value.get("ssh_host", "otp@opitop")),
        str(value.get("remote_binary", "autocode-local")),
        "midi-action",
        action,
        str(value.get("workspace", "/home/otp/Projects/flux2")),
    ]


def _run(config: dict[str, Any], action: str, timeout: float = 30) -> dict[str, Any]:
    if not enabled(config):
        raise RuntimeError("Autocode integration is disabled")
    command = ssh_command(config, action)
    emit("autocode_action_requested", action=action, command=command)
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        emit("autocode_action_result", action=action, ok=False, error="timeout")
        raise RuntimeError(f"Autocode SSH action timed out: {action}") from exc
    stdout = (result.stdout or "")[-MAX_RESPONSE_BYTES:]
    stderr = (result.stderr or "")[-MAX_RESPONSE_BYTES:]
    response = {
        "ok": result.returncode == 0,
        "action": action,
        "command": command,
        "exit_code": result.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }
    emit("autocode_action_result", **response)
    return response


def perform_action(config: dict[str, Any], action: str) -> dict[str, Any]:
    return _run(config, action)


def read_state(config: dict[str, Any]) -> dict[str, Any]:
    result = _run(config, "status")
    if not result["ok"]:
        raise RuntimeError(
            (result["stderr"] or result["stdout"] or "Autocode state query failed").strip()
        )
    raw = result["stdout"].strip()
    if len(raw.encode("utf-8", errors="replace")) > MAX_RESPONSE_BYTES:
        raise RuntimeError("Autocode state response exceeds 64 KiB")
    try:
        outer = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Autocode state response is not JSON") from exc
    state = outer.get("state", outer) if isinstance(outer, dict) else None
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise RuntimeError("unsupported Autocode MIDI state schema")
    selected = str(state.get("state", "idle"))
    if selected not in AUTOCODE_STATES:
        raise RuntimeError(f"unsupported Autocode MIDI state: {selected}")
    return state


def windows_audio_cue(state: str) -> dict[str, Any]:
    try:
        import winsound
    except ImportError:
        return {"played": False, "method": "unavailable"}
    kind = (
        winsound.MB_ICONHAND
        if state == "failed"
        else winsound.MB_ICONEXCLAMATION
        if state == "attention"
        else winsound.MB_OK
    )
    try:
        winsound.MessageBeep(kind)
    except RuntimeError:
        return {"played": False, "method": "winsound"}
    return {"played": True, "method": "winsound", "state": state}


class StateWatcher:
    def __init__(
        self,
        config: dict[str, Any],
        callback: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.config = config
        self.callback = callback
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.last_sequence: int | None = None

    def start(self) -> None:
        if not enabled(self.config):
            return
        if self.thread is not None:
            raise RuntimeError("Autocode state watcher is already running")
        self.thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="midiwin-autocode-state",
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=3)

    def _loop(self) -> None:
        interval = float(settings(self.config).get("poll_seconds", 1.0))
        while not self.stop_event.wait(interval):
            try:
                state = read_state(self.config)
            except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
                emit("autocode_state_error", error=str(exc))
                continue
            sequence = int(state.get("sequence", 0))
            if sequence == self.last_sequence:
                continue
            self.last_sequence = sequence
            emit("autocode_state", state=state)
            if self.callback is not None:
                self.callback(state)
            value = settings(self.config)
            if (
                bool(value.get("audio_cue", True))
                and bool(state.get("cue_pending"))
                and state.get("state") in {"attention", "completed", "failed"}
            ):
                result = windows_audio_cue(str(state["state"]))
                emit("autocode_audio_cue", **result)
