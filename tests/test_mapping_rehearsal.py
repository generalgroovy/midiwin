import copy
import itertools
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from midiwin import gui
from midiwin.common import ControlEvent
from midiwin.gui_support import mapping_rows, save_profile
from midiwin.mapping_inspector import mapping_details, preview_text
from midiwin.mapping_rules import preview_event
from midiwin.router import EventRouter

LINUX = False


def fixture():
    return {"active_profile": "main", "layout_rules": {"no_repeated_actions_per_controller": False}, "mappings": [
        {"device": "f1", "control": "grid_1", "kind": "press", "action": "normal", "unless": ["f1.shift"], "step": 17},
        {"device": "f1", "control": "grid_1", "kind": "press", "action": "layer", "requires": ["f1.shift"]},
        {"device": "f1", "control": "grid_1", "kind": "release", "action": "release"},
        {"device": "f1", "control": "grid_1", "kind": "press", "action": "disabled", "enabled": False},
        {"device": "f1", "control": "shift", "kind": "release", "action": "release_shift", "requires": ["f1.shift"]},
        {"device": "f1", "control": "grid_1", "kind": "press", "action": "other", "profile": "other"},
    ]}


class MappingRehearsalTests(unittest.TestCase):
    def test_windows_rejects_unholdable_or_unqualified_modifiers(self):
        for held in ("shift", "f1.grid_1", "f1:shift"):
            with self.assertRaises(ValueError):
                preview_event(fixture(), "f1", "grid_1", "press", held)
        report = preview_event(fixture(), "f1", "shift", "release", "f1.shift")
        self.assertEqual(report["decisions"][0][2], ["Hold f1.shift"])

    def test_preview_matches_runtime_dispatch_for_layered_event_matrix(self):
        config = fixture()
        # Every combination checks a real router with the action sink replaced.
        for control, kind, held in itertools.product(("grid_1", "shift", "missing"), ("press", "release", "relative", "absolute"), ("", "f1.shift", "x1.hotcue")):
            with self.subTest(control=control, kind=kind, held=held), patch.object(gui.subprocess, "Popen", side_effect=AssertionError("preview started a process")), patch.object(gui.subprocess, "run", side_effect=AssertionError("preview ran a command")):
                with patch(EventRouter.__module__ + ".ActionDispatcher") as dispatcher:
                    router = EventRouter(config, monitor=False)
                    if LINUX:
                        router.held = {tuple(v.split(".")) for v in held.split()}
                    else:
                        router.modifiers = set(held.split())
                    router.emit(ControlEvent("f1", control, kind, 1))
                    dispatched = [call.args[0] for call in dispatcher.return_value.dispatch.call_args_list]
                    dispatcher.reset_mock()
                    report = preview_event(config, "f1", control, kind, held)
                    eligible = [mapping for _, mapping, reasons in report["decisions"] if not reasons]
                    self.assertEqual(dispatched, eligible)
                    dispatcher.assert_not_called()
                    dispatcher.return_value.dispatch.assert_not_called()

    def test_disabled_kind_and_layer_explanations(self):
        report = preview_event(fixture(), "f1", "grid_1", "press", "f1.shift")
        text = preview_text(report)
        self.assertIn("Release f1.shift", text)
        self.assertIn("Needs release", text)
        self.assertIn("Disabled", text)
        self.assertIn("layer", text)
        self.assertIn("no actions run", text)

    def test_malformed_constraints_fail_closed_in_preview_and_runtime(self):
        for bad in (None, 7, {"shift": True}, [False], [" "]):
            config = {"mappings": [{"device": "f1", "control": "grid_1", "kind": "press", "action": "custom", "requires": bad}]}
            with self.subTest(bad=bad), patch(EventRouter.__module__ + ".ActionDispatcher") as dispatcher:
                report = preview_event(config, "f1", "grid_1", "press")
                self.assertIn("Invalid", report["decisions"][0][2][0])
                router = EventRouter(config, monitor=False)
                router.emit(ControlEvent("f1", "grid_1", "press", 1))
                dispatcher.return_value.dispatch.assert_not_called()

    def test_unknown_custom_action_and_script_are_only_data(self):
        config = fixture()
        config["mappings"][0].update(action="script_slot", slot="custom")
        config["script_slots"] = {"custom": {"command": ["DO_NOT_EXECUTE"], "enabled": True}}
        original = copy.deepcopy(config)
        with patch("subprocess.run", side_effect=AssertionError("executed")), patch("subprocess.Popen", side_effect=AssertionError("executed")), patch(EventRouter.__module__ + ".ActionDispatcher", side_effect=AssertionError("created action runner")):
            text = mapping_details(config, config["mappings"][0])
            self.assertIn("DO_NOT_EXECUTE", text)
            preview_event(config, "f1", "grid_1", "press")
        self.assertEqual(config, original)

    def test_search_includes_parameters_and_keeps_real_indices(self):
        config = fixture()
        self.assertEqual(mapping_rows(config, "17")[0][0], "0")
        self.assertEqual(mapping_rows(config, "other")[0][0], "5")
        self.assertEqual(mapping_rows(config, "", "Disabled")[0][0], "3")
        self.assertEqual(mapping_rows(config, "no-match"), [])

    def test_invalid_input_does_not_run_anything(self):
        for device, control, kind in (("", "grid_1", "press"), ("f1", "", "press"), ("f1", "grid_1", "invalid")):
            with self.assertRaises(ValueError):
                preview_event(fixture(), device, control, kind)

    def test_atomic_save_failure_preserves_original_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "profile.json"
            path.write_bytes(b"original")
            with patch(gui.save_profile.__module__ + ".os.replace", side_effect=OSError("busy")), self.assertRaises(OSError):
                save_profile(path, {"unicode": "音"})
            self.assertEqual(path.read_bytes(), b"original")
            self.assertEqual(list(Path(folder).iterdir()), [path])
            save_profile(path, {"unicode": "音"})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"unicode": "音"})

    def draft(self):
        view = gui.MidiWinGui.__new__(gui.MidiWinGui)
        view.root = Mock()
        view.settings_baseline = ("1",)
        view.settings_snapshot = Mock(return_value=("2",))
        view.save_settings = Mock(return_value=True)
        view.stop_process = Mock()
        return view

    def test_close_cancel_preserves_draft_and_running_monitor(self):
        view = self.draft()
        with patch.object(gui.messagebox, "askyesnocancel", return_value=None):
            view.close()
        view.stop_process.assert_not_called()
        view.root.destroy.assert_not_called()

    def test_failed_save_does_not_close_or_reload(self):
        view = self.draft()
        view.save_settings.return_value = False
        with patch.object(gui.messagebox, "askyesnocancel", return_value=True):
            view.close()
            self.assertFalse(view.reload())
        view.stop_process.assert_not_called()
        view.root.destroy.assert_not_called()

    def test_discard_closes_and_unchanged_close_does_not_prompt(self):
        view = self.draft()
        with patch.object(gui.messagebox, "askyesnocancel", return_value=False):
            view.close()
        view.stop_process.assert_called_once()
        view.root.destroy.assert_called_once()
        view = self.draft()
        view.settings_snapshot.return_value = ("1",)
        with patch.object(gui.messagebox, "askyesnocancel") as ask:
            view.close()
            ask.assert_not_called()

    def test_reload_cancel_does_not_even_read_profile(self):
        view = self.draft()
        with patch.object(gui.messagebox, "askyesnocancel", return_value=None), patch.object(gui, "load_config") as load:
            self.assertFalse(view.reload())
            load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
