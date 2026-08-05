from __future__ import annotations

import json
import os
from pathlib import Path

from midiwin.common import validate_config
from midiwin.eventlog import clear, emit, event_path, read_tail, redact


def test_event_ledger_is_append_only_redacted_and_clearable(tmp_path: Path, monkeypatch):
    target = tmp_path / "events.jsonl"
    monkeypatch.setenv("MIDIWIN_EVENT_LOG", str(target))

    first = emit("test", message="password=hunter2", nested={"token": "token=abc"})
    second = emit("test", value=2)

    assert first["message"] == "password=<REDACTED>"
    assert first["nested"]["token"] == "token=<REDACTED>"
    assert second["value"] == 2
    assert event_path() == target
    assert [item["value"] for item in read_tail(1)] == [2]
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["schema_version"] == 1 for line in lines)
    assert "hunter2" not in target.read_text(encoding="utf-8")
    assert clear()
    assert not target.exists()


def test_redaction_handles_bearer_and_openai_shaped_secrets():
    rendered = redact("Authorization: Bearer secret sk-abcdefghijklmnop")
    assert "secret" not in rendered
    assert "sk-abcdefghijklmnop" not in rendered
    assert rendered.count("<REDACTED>") == 2


def test_validation_rejects_ambiguous_and_impossible_modifier_conditions():
    base = {
        "device": "f1",
        "control": "grid_1",
        "kind": "press",
        "action": "open_browser",
        "requires": ["f1.shift"],
        "unless": [],
    }
    duplicate = {**base, "action": "open_terminal"}
    impossible = {
        **base,
        "control": "grid_2",
        "requires": ["f1.shift"],
        "unless": ["f1.shift"],
    }

    errors = validate_config({"mappings": [base, duplicate, impossible]})

    assert any("ambiguous mapping" in error for error in errors)
    assert any("requires and excludes" in error for error in errors)


def test_disabled_duplicate_does_not_block_runtime_configuration():
    mapping = {
        "device": "f1",
        "control": "grid_1",
        "kind": "press",
        "action": "open_browser",
    }
    assert validate_config({"mappings": [mapping, {**mapping, "enabled": False}]}) == []
