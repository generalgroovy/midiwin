from pathlib import Path

from midiwin.actions import ActionDispatcher
from midiwin.common import ControlEvent, load_config, validate_config
from midiwin.gui import _mapping_index


def test_default_has_brightness_and_gui_mapping():
    config = load_config(Path("config.default.json"))
    assert validate_config(config) == []
    mapping = _mapping_index(config)[("f1", "knob_4")]
    assert mapping["action"] == "brightness_absolute"
    assert config["display_controls"]["brightness"]["minimum_percent"] == 1


def test_brightness_dry_run_is_safe():
    config = load_config(Path("config.default.json"))
    dispatcher = ActionDispatcher(config, dry_run=True)
    assert dispatcher.set_brightness_percent(50)
    dispatcher.dispatch(
        {"action": "brightness_absolute"},
        ControlEvent("f1", "knob_4", "absolute", 2048, 0, 4096),
    )
