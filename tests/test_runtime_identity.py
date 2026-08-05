from __future__ import annotations

import getpass
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import midiwin.cli as cli


class FakeProcess:
    def __init__(
        self,
        pid: int = 42,
        *,
        name: str = "MIDIWIN.exe",
        command_line: list[str] | None = None,
        username: str | None = None,
        create_time: float = 100.0,
        running: bool = True,
    ) -> None:
        self.pid = pid
        self._name = name
        self._command_line = command_line or ["MIDIWIN.exe"]
        self._username = username or getpass.getuser()
        self._create_time = create_time
        self._running = running
        self.terminated = False
        self.killed = False

    def is_running(self) -> bool:
        return self._running

    def name(self) -> str:
        return self._name

    def cmdline(self) -> list[str]:
        return self._command_line

    def username(self) -> str:
        return self._username

    def create_time(self) -> float:
        return self._create_time

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        self._running = False
        return 0


class NoSuchProcess(Exception):
    pass


class ZombieProcess(Exception):
    pass


class AccessDenied(Exception):
    pass


class TimeoutExpired(Exception):
    pass


def fake_psutil(process_or_error):
    def process_factory(_pid: int):
        if isinstance(process_or_error, BaseException):
            raise process_or_error
        return process_or_error

    return SimpleNamespace(
        Process=process_factory,
        NoSuchProcess=NoSuchProcess,
        ZombieProcess=ZombieProcess,
        AccessDenied=AccessDenied,
        TimeoutExpired=TimeoutExpired,
    )


def write_identity(path: Path, **changes) -> None:
    value = {
        "schema_version": 1,
        "pid": 42,
        "create_time": 100.0,
        "username": getpass.getuser(),
    }
    value.update(changes)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_runtime_process_requires_matching_creation_time_user_and_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pid_file = tmp_path / "runtime.pid"
    monkeypatch.setattr(cli, "PID_FILE", pid_file)

    valid = FakeProcess()
    write_identity(pid_file)
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil(valid))
    assert cli._runtime_process() is valid
    assert pid_file.exists()

    stale = FakeProcess(create_time=101.0)
    write_identity(pid_file)
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil(stale))
    assert cli._runtime_process() is None
    assert not pid_file.exists()

    unrelated = FakeProcess(name="python.exe", command_line=["python", "worker.py"])
    write_identity(pid_file)
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil(unrelated))
    assert cli._runtime_process() is None
    assert not pid_file.exists()


def test_unverifiable_runtime_fails_closed_without_deleting_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pid_file = tmp_path / "runtime.pid"
    monkeypatch.setattr(cli, "PID_FILE", pid_file)
    write_identity(pid_file)
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil(AccessDenied()))

    with pytest.raises(RuntimeError, match="access denied"):
        cli._runtime_process()
    assert pid_file.exists()


def test_stop_runtime_terminates_only_verified_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pid_file = tmp_path / "runtime.pid"
    event_log = tmp_path / "events.jsonl"
    monkeypatch.setattr(cli, "PID_FILE", pid_file)
    monkeypatch.setenv("MIDIWIN_EVENT_LOG", str(event_log))
    process = FakeProcess()
    write_identity(pid_file)
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil(process))

    assert cli.stop_runtime()
    assert process.terminated
    assert not process.killed
    assert not pid_file.exists()
    kinds = [item["kind"] for item in cli.read_tail(20)]
    assert "runtime_stop_requested" in kinds
    assert "runtime_stopped" in kinds


def test_json_status_exposes_retention_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cli, "PID_FILE", tmp_path / "runtime.pid")
    monkeypatch.setattr(cli, "_runtime_process", lambda: None)
    monkeypatch.setattr(cli, "list_devices", lambda: ["F1 test device"])
    monkeypatch.setenv("MIDIWIN_EVENT_LOG", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("MIDIWIN_EVENT_LOG_MODE", "actions")
    monkeypatch.setenv("MIDIWIN_EVENT_LOG_MAX_BYTES", "4096")
    monkeypatch.setenv("MIDIWIN_EVENT_LOG_BACKUPS", "2")

    status = cli._status(None)
    event_log = status["event_log"]
    assert event_log["mode"] == "actions"
    assert event_log["max_bytes"] == 4096
    assert event_log["backup_count"] == 2
    assert len(event_log["segments"]) == 3


def test_legacy_pid_only_identity_is_rejected_and_removed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pid_file = tmp_path / "runtime.pid"
    monkeypatch.setattr(cli, "PID_FILE", pid_file)
    pid_file.write_text("42", encoding="ascii")
    process = FakeProcess(create_time=999.0)
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil(process))

    assert cli._runtime_process() is None
    assert not pid_file.exists()
    assert not process.terminated
