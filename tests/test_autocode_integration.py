from __future__ import annotations

import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from midiwin import autocode
from midiwin.common import ControlEvent, load_config, validate_config
from midiwin.router import EventRouter


class AutocodeIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = {
            "autocode": {
                "enabled": True,
                "transport": "ssh",
                "ssh_binary": "ssh.exe",
                "ssh_host": "otp@opitop",
                "remote_binary": "autocode-local",
                "workspace": "/home/otp/Projects/flux2",
                "connect_timeout_seconds": 5,
                "poll_seconds": 0.25,
                "audio_cue": True,
            },
            "mappings": [],
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_real_default_config_is_valid_and_integration_is_opt_in(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        config = load_config(repository / "config.default.json")
        self.assertEqual([], validate_config(config))
        self.assertFalse(config["autocode"]["enabled"])
        actions = {
            mapping["action"]
            for mapping in config["mappings"]
            if str(mapping.get("action", "")).startswith("autocode_")
        }
        self.assertIn("autocode_pause", actions)
        self.assertIn("autocode_acknowledge", actions)

    @mock.patch("midiwin.autocode.shutil.which")
    def test_ssh_command_is_encrypted_fixed_and_noninteractive(self, which: mock.Mock) -> None:
        which.return_value = r"C:\Windows\System32\OpenSSH\ssh.exe"
        command = autocode.ssh_command(self.config, "pause")
        self.assertEqual(r"C:\Windows\System32\OpenSSH\ssh.exe", command[0])
        self.assertIn("BatchMode=yes", command)
        self.assertIn("ConnectTimeout=5", command)
        self.assertIn("RequestTTY=no", command)
        self.assertEqual(
            [
                "otp@opitop",
                "autocode-local",
                "midi-action",
                "pause",
                "/home/otp/Projects/flux2",
            ],
            command[-5:],
        )
        self.assertNotIn("powershell.exe", command)
        self.assertNotIn("cmd.exe", command)

    def test_host_binary_workspace_and_action_injection_fail_closed(self) -> None:
        for change, expected in (
            ({"ssh_host": "otp@opitop;calc.exe"}, "ssh_host"),
            ({"remote_binary": "autocode-local && calc.exe"}, "remote_binary"),
            ({"workspace": "/home/otp/Projects/flux 2"}, "absolute POSIX path"),
            ({"workspace": "/home/otp/../root"}, "absolute POSIX path"),
        ):
            config = {**self.config, "autocode": {**self.config["autocode"], **change}}
            self.assertTrue(any(expected in error for error in autocode.validate(config)))
        with self.assertRaisesRegex(ValueError, "unsupported Autocode action"):
            autocode.ssh_command(self.config, "arbitrary-shell")

    @mock.patch("midiwin.autocode.subprocess.run")
    @mock.patch("midiwin.autocode.shutil.which")
    def test_state_query_parses_only_supported_nested_schema(
        self,
        which: mock.Mock,
        run: mock.Mock,
    ) -> None:
        which.return_value = "ssh.exe"
        state = {
            "schema_version": 1,
            "sequence": 7,
            "state": "completed",
            "cue_pending": True,
            "workspace": "/home/otp/Projects/flux2",
        }
        run.return_value = subprocess.CompletedProcess(
            [], 0, stdout=json.dumps({"ok": True, "action": "status", "state": state}), stderr=""
        )
        self.assertEqual(state, autocode.read_state(self.config))
        run.return_value = subprocess.CompletedProcess(
            [], 0, stdout=json.dumps({"state": {"schema_version": 99}}), stderr=""
        )
        with self.assertRaisesRegex(RuntimeError, "unsupported"):
            autocode.read_state(self.config)

    def test_router_dry_run_never_opens_ssh_process(self) -> None:
        config = {
            **self.config,
            "mappings": [
                {
                    "device": "f1",
                    "control": "grid_7",
                    "kind": "press",
                    "action": "autocode_pause",
                    "requires": ["f1.shift"],
                }
            ],
        }
        router = EventRouter(config, dry_run=True)
        router.modifiers.add("f1.shift")
        with mock.patch("midiwin.router.perform_action") as action:
            router.emit(ControlEvent("f1", "grid_7", "press", 1))
        action.assert_not_called()

    @mock.patch("midiwin.router.perform_action")
    def test_router_translates_mapping_to_closed_remote_action(self, action: mock.Mock) -> None:
        action.return_value = {"ok": True, "action": "pause"}
        config = {
            **self.config,
            "mappings": [
                {
                    "device": "f1",
                    "control": "grid_7",
                    "kind": "press",
                    "action": "autocode_pause",
                    "requires": ["f1.shift"],
                }
            ],
        }
        router = EventRouter(config)
        router.modifiers.add("f1.shift")
        router.emit(ControlEvent("f1", "grid_7", "press", 1))
        action.assert_called_once_with(config, "pause")

    def test_watcher_emits_and_cues_only_new_pending_sequences(self) -> None:
        states = [
            {"schema_version": 1, "sequence": 1, "state": "running", "cue_pending": False},
            {"schema_version": 1, "sequence": 2, "state": "completed", "cue_pending": True},
            {"schema_version": 1, "sequence": 2, "state": "completed", "cue_pending": True},
        ]
        callback = mock.Mock()
        watcher = autocode.StateWatcher(self.config, callback)
        with mock.patch("midiwin.autocode.read_state", side_effect=states), mock.patch(
            "midiwin.autocode.windows_audio_cue"
        ) as cue:
            watcher.start()
            time.sleep(0.9)
            watcher.stop()
        self.assertGreaterEqual(callback.call_count, 2)
        cue.assert_called_once_with("completed")

    @mock.patch("midiwin.autocode.shutil.which", return_value="ssh.exe")
    def test_disabled_integration_does_not_execute(self, _which: mock.Mock) -> None:
        config = {**self.config, "autocode": {**self.config["autocode"], "enabled": False}}
        with mock.patch("midiwin.autocode.subprocess.run") as run:
            with self.assertRaisesRegex(RuntimeError, "disabled"):
                autocode.perform_action(config, "status")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
