from __future__ import annotations

import os
from pathlib import Path

import pytest

from midiwin.eventlog import clear, emit, event_files, event_path, read_tail


def test_rotates_reads_across_segments_and_clears(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "events.jsonl"
    monkeypatch.setenv("MIDIWIN_EVENT_LOG", str(target))
    monkeypatch.setenv("MIDIWIN_EVENT_LOG_MAX_BYTES", "1024")
    monkeypatch.setenv("MIDIWIN_EVENT_LOG_BACKUPS", "2")
    monkeypatch.setenv("MIDIWIN_EVENT_LOG_MODE", "full")

    for sequence in range(12):
        emit("test", sequence=sequence, payload="x" * 300)

    assert target.exists()
    assert target.with_name("events.jsonl.1").exists()
    assert [item["sequence"] for item in read_tail(3)] == [9, 10, 11]
    assert clear()
    assert not any(path.exists() for path in event_files())


def test_actions_mode_suppresses_high_volume_routing_noise(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "events.jsonl"
    monkeypatch.setenv("MIDIWIN_EVENT_LOG", str(target))
    monkeypatch.setenv("MIDIWIN_EVENT_LOG_MODE", "actions")

    emit("control_input", value=1)
    emit("mapping_unmatched", control="knob_1")
    emit("mapping_selected", action="volume_absolute")

    assert [item["kind"] for item in read_tail(10)] == ["mapping_selected"]


def test_off_mode_creates_no_ledger(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "events.jsonl"
    monkeypatch.setenv("MIDIWIN_EVENT_LOG", str(target))
    monkeypatch.setenv("MIDIWIN_EVENT_LOG_MODE", "off")

    event = emit("mapping_selected", action="volume_absolute")

    assert event["kind"] == "mapping_selected"
    assert not target.exists()
    assert read_tail(10) == []


def test_invalid_limits_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MIDIWIN_EVENT_LOG", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("MIDIWIN_EVENT_LOG_MAX_BYTES", "100")
    with pytest.raises(ValueError, match="between"):
        emit("test")


@pytest.mark.skipif(os.name == "nt", reason="Windows CI may not grant symlink creation privileges")
def test_symbolic_link_log_target_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.jsonl"
    outside.write_text("outside\n", encoding="utf-8")
    target = tmp_path / "events.jsonl"
    target.symlink_to(outside)
    monkeypatch.setenv("MIDIWIN_EVENT_LOG", str(target))

    with pytest.raises(RuntimeError, match="symbolic link"):
        emit("test")
    assert outside.read_text(encoding="utf-8") == "outside\n"


def test_posix_event_files_are_private(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX modes are not authoritative on Windows")
    target = tmp_path / "state" / "events.jsonl"
    monkeypatch.setenv("MIDIWIN_EVENT_LOG", str(target))
    emit("test")
    assert event_path() == target
    assert target.parent.stat().st_mode & 0o777 == 0o700
    assert target.stat().st_mode & 0o777 == 0o600
