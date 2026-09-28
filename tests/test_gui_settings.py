import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from midiwin.gui import MidiWinGui
from midiwin import gui as gui_module
from midiwin.common import load_config


class Value:
    def __init__(self, value): self.value = value
    def get(self): return self.value
    def set(self, value): self.value = value


def console(tmp_path):
    path = tmp_path / 'profile.json'
    path.write_text(Path('config.default.json').read_text(encoding='utf-8'), encoding='utf-8')
    view = MidiWinGui.__new__(MidiWinGui)
    view.config_path = view.requested_config_path = path
    view.config = load_config(path)
    view.brightness_display = Value('stale')
    view.min_brightness = Value(99)
    view.canvas = Mock()
    view._fill_mappings = Mock()
    view.status = Value('Ready')
    return view


def test_reload_refreshes_editable_fields_and_preserves_display_zero(tmp_path):
    view = console(tmp_path)
    data = view.config
    data['display_controls']['brightness'].update(display=0, minimum_percent=7)
    view.config_path.write_text(json.dumps(data), encoding='utf-8')
    view.reload()
    assert view.brightness_display.get() == '0'
    assert view.min_brightness.get() == 7
    view.save_settings()
    assert view.status.get() == 'Configuration saved'
    assert load_config(view.config_path)['display_controls']['brightness']['minimum_percent'] == 7


@pytest.mark.parametrize('minimum', [-1, 101, 'invalid'])
def test_invalid_form_does_not_write_profile(tmp_path, monkeypatch, minimum):
    view = console(tmp_path)
    before = view.config_path.read_bytes()
    view.min_brightness.set(minimum)
    error = Mock()
    monkeypatch.setattr(gui_module.messagebox, 'showerror', error)
    view.save_settings()
    assert view.config_path.read_bytes() == before
    error.assert_called_once()


def test_first_launch_open_config_explains_save_without_launching(tmp_path, monkeypatch):
    view = console(tmp_path)
    view.config_path = tmp_path / 'not-saved.json'
    launch = Mock()
    info = Mock()
    monkeypatch.setattr(gui_module.os, 'startfile', launch, raising=False)
    monkeypatch.setattr(gui_module.messagebox, 'showinfo', info)
    view.open_config()
    launch.assert_not_called()
    info.assert_called_once()
