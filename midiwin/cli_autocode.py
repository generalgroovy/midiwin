from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from . import cli as base
from .autocode import AUTOCODE_ACTIONS, StateWatcher, enabled, perform_action, read_state, settings
from .common import APP_DIR, load_config


_BASE_STATUS = base._status
_BASE_RUN_RUNTIME = base.run_runtime


def _config_argument(arguments: list[str]) -> Path | None:
    for index, value in enumerate(arguments):
        if value == "--config" and index + 1 < len(arguments):
            return Path(arguments[index + 1])
        if value.startswith("--config="):
            return Path(value.split("=", 1)[1])
    return None


def _status(config_path: Path | None) -> dict[str, object]:
    value = _BASE_STATUS(config_path)
    config = load_config(config_path)
    state: dict[str, Any]
    if not enabled(config):
        state = {"available": False, "state": "disabled"}
    else:
        try:
            state = read_state(config)
            state["available"] = True
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            state = {"available": False, "error": str(exc)}
    value["autocode"] = {
        "enabled": enabled(config),
        "transport": settings(config).get("transport", "ssh"),
        "host": settings(config).get("ssh_host", "otp@opitop"),
        "workspace": settings(config).get(
            "workspace", "/home/otp/Projects/flux2"
        ),
        "state": state,
        "actions": sorted(AUTOCODE_ACTIONS),
        "arbitrary_commands": False,
        "controller_led_feedback": False,
        "windows_audio_feedback": bool(settings(config).get("audio_cue", True)),
    }
    return value


def _special(arguments: list[str]) -> int | None:
    config_path = _config_argument(arguments)
    config = load_config(config_path)
    if "--autocode-state" in arguments:
        print(json.dumps(read_state(config), indent=2, ensure_ascii=False))
        return 0
    if "--autocode-action" in arguments:
        index = arguments.index("--autocode-action")
        if index + 1 >= len(arguments):
            raise SystemExit("--autocode-action requires an action name")
        action = arguments[index + 1]
        if action not in AUTOCODE_ACTIONS:
            raise SystemExit(
                "Unsupported Autocode action; choose one of: "
                + ", ".join(sorted(AUTOCODE_ACTIONS))
            )
        result = perform_action(config, action)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok", False) else 1
    return None


def _runtime_with_watcher(
    config: dict[str, Any],
) -> Callable[[Callable[[Any], None]], None]:
    def run(emit_control: Callable[[Any], None]) -> None:
        watcher = StateWatcher(config)
        watcher.start()
        try:
            _BASE_RUN_RUNTIME(emit_control)
        finally:
            watcher.stop()

    return run


def main() -> int:
    arguments = sys.argv[1:]
    special = _special(arguments)
    if special is not None:
        return special
    config_path = _config_argument(arguments)
    config = load_config(config_path)
    base._status = _status
    base.run_runtime = _runtime_with_watcher(config)
    return base.main()
