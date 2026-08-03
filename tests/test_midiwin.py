from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from midiwin.common import ControlEvent, load_config, validate_config
from midiwin.hardware import _normalize_f1_report
from midiwin.router import EventRouter


class FakeDispatcher:
    def __init__(self):
        self.actions: list[str] = []

    def dispatch(self, mapping, event):
        action = mapping["action"]
        if action == "script_slot":
            action += ":" + mapping["slot"]
        self.actions.append(action)


def test_default_config_is_valid():
    config = load_config(Path("config.default.json"))
    assert validate_config(config) == []
    assert len(config["mappings"]) >= 20


def test_control_event_ratio_is_clamped():
    assert ControlEvent("f1", "knob_1", "absolute", 2048, 0, 4096).ratio == 0.5
    assert ControlEvent("f1", "knob_1", "absolute", 5000, 0, 4096).ratio == 1.0


def test_f1_report_normalization():
    report = bytes(range(21))
    normalized = _normalize_f1_report(report)
    assert normalized is not None
    assert normalized[0] == 1
    assert len(normalized) == 22


def test_shift_layer_is_exclusive():
    config = load_config(Path("config.default.json"))
    router = EventRouter(config, dry_run=True)
    fake = FakeDispatcher()
    router.dispatcher = fake

    router.emit(ControlEvent("f1", "grid_1", "press", 1))
    assert fake.actions == ["open_browser"]

    fake.actions.clear()
    router.emit(ControlEvent("f1", "shift", "press", 1))
    router.emit(ControlEvent("f1", "grid_1", "press", 1))
    assert fake.actions == ["script_slot:codex"]


def test_close_window_binding_is_unique():
    config = load_config(Path("config.default.json"))
    matches = [
        mapping for mapping in config["mappings"]
        if mapping.get("action") == "close_focused_window"
    ]
    assert len(matches) == 1
    assert matches[0]["device"] == "f1"
    assert matches[0]["control"] == "reverse"
