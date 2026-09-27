import json
from pathlib import Path

import pytest

from midiwin.cli import main
from midiwin.common import load_config, validate_config
from midiwin.gui import MidiWinGui
from types import SimpleNamespace
from unittest.mock import Mock


@pytest.mark.parametrize('field', ['requires', 'unless'])
@pytest.mark.parametrize('value', [None, 'f1.shift', 4, [{}], ['']])
def test_invalid_modifier_list_is_reported(field, value):
    mapping = dict(device='f1', control='grid_1', kind='press', action='open_browser')
    mapping[field] = value
    assert f'mapping 0 {field} must be an array of modifier names' in validate_config({'mappings': [mapping]})


def test_explicit_missing_configuration_is_not_replaced_with_defaults(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / 'missing.json')


def test_contradictory_modifiers_are_reported():
    mapping = dict(device='f1', control='grid_1', kind='press', action='open_browser', requires=['f1.shift'], unless=['f1.shift'])
    assert 'mapping 0 requires and excludes the same modifier' in validate_config({'mappings': [mapping]})


def test_cli_invalid_json_explains_error_without_traceback(tmp_path, monkeypatch, capsys):
    path = tmp_path / 'bad.json'
    path.write_text('{bad', encoding='utf-8')
    monkeypatch.setattr('sys.argv', ['midiwin', '--config', str(path), '--validate-config'])
    assert main() == 1
    assert 'Configuration error:' in capsys.readouterr().out


def test_layout_rejects_invalid_modifiers_before_rendering(tmp_path, monkeypatch, capsys):
    config = load_config(Path('config.default.json'))
    config['mappings'][0]['requires'] = None
    path = tmp_path / 'bad.json'
    path.write_text(json.dumps(config), encoding='utf-8')
    monkeypatch.setattr('sys.argv', ['midiwin', '--config', str(path), '--show-layout'])
    assert main() == 1
    assert 'requires must be an array' in capsys.readouterr().out


def test_first_gui_launch_uses_defaults_without_creating_a_profile(tmp_path, monkeypatch):
    monkeypatch.setattr('midiwin.common.APP_DIR', tmp_path)
    monkeypatch.setattr('midiwin.gui.APP_DIR', tmp_path)
    monkeypatch.setattr(MidiWinGui, '_build', lambda self: None)
    gui = MidiWinGui(Mock())
    assert validate_config(gui.config) == []
    assert gui.python_command() == [__import__('sys').executable, '-m', 'midiwin']
    assert not (tmp_path / 'config.json').exists()


def test_gui_custom_config_is_forwarded_to_controller(tmp_path, monkeypatch):
    path = tmp_path / 'custom.json'
    path.write_text(Path('config.default.json').read_text(), encoding='utf-8')
    monkeypatch.setattr(MidiWinGui, '_build', lambda self: None)
    gui = MidiWinGui(Mock(), path)
    assert gui.python_command()[-2:] == ['--config', str(path)]


def test_gui_can_save_its_first_default_profile(tmp_path, monkeypatch):
    monkeypatch.setattr('midiwin.common.APP_DIR', tmp_path)
    monkeypatch.setattr('midiwin.gui.APP_DIR', tmp_path)
    monkeypatch.setattr(MidiWinGui, '_build', lambda self: None)
    gui = MidiWinGui(Mock())
    gui.brightness_display = SimpleNamespace(get=lambda: '')
    gui.min_brightness = SimpleNamespace(get=lambda: '5')
    gui.status = Mock()
    gui.reload = Mock()
    gui.save_settings()
    saved = json.loads((tmp_path / 'config.json').read_text())
    assert saved['display_controls']['brightness']['minimum_percent'] == 5
    gui.reload.assert_called_once()


def test_device_diagnostics_work_with_invalid_mappings(tmp_path, monkeypatch, capsys):
    path = tmp_path / 'invalid.json'
    path.write_text('{"mappings": null}', encoding='utf-8')
    devices = Mock(return_value=['F1 example device'])
    monkeypatch.setattr('midiwin.cli.list_devices', devices)
    monkeypatch.setattr('sys.argv', ['midiwin', '--config', str(path), '--list-devices'])
    assert main() == 0
    devices.assert_called_once()
    assert 'F1 example device' in capsys.readouterr().out


def test_gui_relative_configuration_is_resolved_before_child_launch(tmp_path, monkeypatch):
    config_text = Path('config.default.json').read_text()
    path = tmp_path / 'custom.json'
    path.write_text(config_text, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(MidiWinGui, '_build', lambda self: None)
    gui = MidiWinGui(Mock(), Path('custom.json'))
    assert gui.config_path == path.resolve()
    assert gui.python_command()[-1] == str(path.resolve())
