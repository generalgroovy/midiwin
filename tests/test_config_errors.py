import json
from pathlib import Path

import pytest

from midiwin.cli import main
from midiwin.common import load_config, validate_config


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
