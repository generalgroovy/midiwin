from __future__ import annotations

import argparse
import atexit
import getpass
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .actions import ActionDispatcher
from .common import APP_DIR, load_config, validate_config
from .eventlog import backup_count, clear as clear_events
from .eventlog import emit, event_files, event_path, log_mode, max_bytes, read_tail
from .hardware import list_devices, run_runtime
from .router import EventRouter

PID_FILE = APP_DIR / "runtime.pid"


def _normalize_user(value: str) -> str:
    return value.replace("/", "\\").rsplit("\\", 1)[-1].strip().lower()


def _remove_pid_file() -> None:
    if PID_FILE.is_symlink():
        raise RuntimeError(f"runtime PID file must not be a symbolic link: {PID_FILE}")
    PID_FILE.unlink(missing_ok=True)


def _read_runtime_identity() -> dict[str, Any] | None:
    if PID_FILE.is_symlink():
        raise RuntimeError(f"runtime PID file must not be a symbolic link: {PID_FILE}")
    try:
        text = PID_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    if not text:
        _remove_pid_file()
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        try:
            return {"pid": int(text), "legacy": True}
        except ValueError:
            _remove_pid_file()
            return None
    if not isinstance(value, dict) or not isinstance(value.get("pid"), int):
        _remove_pid_file()
        return None
    return value


def _read_runtime_pid() -> int | None:
    identity = _read_runtime_identity()
    return int(identity["pid"]) if identity else None


def _write_runtime_identity(identity: dict[str, Any]) -> None:
    if PID_FILE.is_symlink():
        raise RuntimeError(f"runtime PID file must not be a symbolic link: {PID_FILE}")
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=".runtime.pid.", dir=PID_FILE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(identity, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(raw, PID_FILE)
    finally:
        if os.path.exists(raw):
            os.unlink(raw)


def _process_matches_identity(process: Any, identity: dict[str, Any]) -> bool:
    if not process.is_running():
        return False
    try:
        name = str(process.name()).lower()
        command_line = " ".join(str(item) for item in process.cmdline()).lower()
        username = str(process.username())
        created = float(process.create_time())
    except Exception:
        return False
    marker_matches = "midiwin" in name or "midiwin" in command_line
    if not marker_matches:
        return False
    expected_user = identity.get("username")
    if expected_user:
        if _normalize_user(username) != _normalize_user(str(expected_user)):
            return False
    elif _normalize_user(username) != _normalize_user(getpass.getuser()):
        return False
    expected_created = identity.get("create_time")
    if expected_created is not None and abs(created - float(expected_created)) > 0.01:
        return False
    return True


def _runtime_process():
    identity = _read_runtime_identity()
    if not identity:
        return None
    try:
        import psutil

        process = psutil.Process(int(identity["pid"]))
        if _process_matches_identity(process, identity):
            return process
    except psutil.NoSuchProcess:
        pass
    except psutil.AccessDenied as exc:
        raise RuntimeError(
            f"cannot verify MIDIWIN runtime PID {identity['pid']}: access denied"
        ) from exc
    _remove_pid_file()
    return None


def stop_runtime() -> bool:
    process = _runtime_process()
    if process is None:
        print("MIDIWIN runtime is not running.")
        emit("runtime_stop_skipped", reason="not-running")
        return False
    import psutil

    emit("runtime_stop_requested", pid=process.pid, create_time=process.create_time())
    process.terminate()
    forced = False
    try:
        process.wait(timeout=4)
    except psutil.TimeoutExpired:
        forced = True
        process.kill()
        process.wait(timeout=4)
    except psutil.NoSuchProcess:
        pass
    _remove_pid_file()
    emit("runtime_stopped", pid=process.pid, forced=forced)
    print(f"Stopped MIDIWIN runtime PID {process.pid}.")
    return True


def claim_runtime() -> None:
    process = _runtime_process()
    if process is not None and process.pid != os.getpid():
        raise SystemExit(
            f"MIDIWIN is already running as PID {process.pid}. "
            "Use `python -m midiwin --stop-runtime` first."
        )
    import psutil

    current = psutil.Process(os.getpid())
    identity = {
        "schema_version": 1,
        "pid": os.getpid(),
        "create_time": current.create_time(),
        "username": current.username(),
        "claimed_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    }
    _write_runtime_identity(identity)
    emit(
        "runtime_claimed",
        pid=os.getpid(),
        create_time=identity["create_time"],
        pid_file=str(PID_FILE),
    )

    def release() -> None:
        try:
            persisted = _read_runtime_identity()
            if (
                persisted
                and persisted.get("pid") == os.getpid()
                and abs(float(persisted.get("create_time", -1)) - float(identity["create_time"]))
                <= 0.01
            ):
                _remove_pid_file()
                emit("runtime_released", pid=os.getpid())
        except (FileNotFoundError, RuntimeError, TypeError, ValueError):
            pass

    atexit.register(release)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="midiwin")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--validate-config", action="store_true")
    parser.add_argument("--show-layout", action="store_true")
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--gui", action="store_true")
    parser.add_argument("--set-brightness", type=int, metavar="PERCENT")
    parser.add_argument("--diagnose-display", action="store_true")
    parser.add_argument("--runtime-status", action="store_true")
    parser.add_argument("--stop-runtime", action="store_true")
    parser.add_argument("--event-log", type=Path, help="Override the JSONL event-ledger path")
    parser.add_argument("--event-tail", type=int, metavar="COUNT")
    parser.add_argument("--clear-event-log", action="store_true")
    parser.add_argument("--json-status", action="store_true")
    return parser


def _status(config_path: Path | None) -> dict[str, object]:
    config = load_config(config_path)
    errors = validate_config(config)
    runtime_error = None
    try:
        process = _runtime_process()
    except RuntimeError as exc:
        process = None
        runtime_error = str(exc)
    try:
        devices = list_devices()
        device_error = None
    except Exception as exc:
        devices = []
        device_error = str(exc)
    path = event_path()
    segments = [
        {
            "path": str(segment),
            "exists": segment.exists(),
            "bytes": segment.stat().st_size if segment.exists() else 0,
        }
        for segment in event_files(path)
    ]
    return {
        "schema_version": 1,
        "application": "midiwin",
        "config": str((config_path or APP_DIR / "config.json").expanduser()),
        "config_valid": not errors,
        "config_errors": errors,
        "enabled_mappings": sum(
            1
            for mapping in config.get("mappings", [])
            if isinstance(mapping, dict) and mapping.get("enabled", True)
        ),
        "runtime": {
            "running": process is not None,
            "pid": process.pid if process is not None else None,
            "create_time": process.create_time() if process is not None else None,
            "pid_file": str(PID_FILE),
            "verification_error": runtime_error,
        },
        "devices": devices,
        "device_error": device_error,
        "event_log": {
            "path": str(path),
            "mode": log_mode(),
            "max_bytes": max_bytes(),
            "backup_count": backup_count(),
            "segments": segments,
            "total_bytes": sum(int(segment["bytes"]) for segment in segments),
            "recent_events": len(read_tail(100)),
        },
    }


def main() -> int:
    args = build_parser().parse_args()
    if args.event_log:
        os.environ["MIDIWIN_EVENT_LOG"] = str(args.event_log.expanduser())
    if args.gui:
        from .gui import main as gui_main

        return gui_main()
    if args.clear_event_log:
        removed = clear_events()
        print(f"Event log {'removed' if removed else 'already absent'}: {event_path()}")
        return 0
    if args.event_tail is not None:
        print(json.dumps(read_tail(args.event_tail), indent=2, ensure_ascii=False))
        return 0
    if args.json_status:
        print(json.dumps(_status(args.config), indent=2, ensure_ascii=False))
        return 0
    if args.stop_runtime:
        return 0 if stop_runtime() else 1
    if args.runtime_status:
        try:
            process = _runtime_process()
        except RuntimeError as exc:
            print(f"MIDIWIN runtime: unverifiable ({exc})")
            return 2
        if process is None:
            print("MIDIWIN runtime: stopped")
            return 1
        print(f"MIDIWIN runtime: running PID {process.pid}")
        return 0

    config = load_config(args.config)
    if args.list_devices:
        devices = list_devices()
        for item in devices:
            print(item)
        return 0 if any(item.startswith(("F1 ", "X1 ")) for item in devices) else 1
    if args.validate_config:
        errors = validate_config(config)
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            return 1
        print(f"Configuration valid: {len(config.get('mappings', []))} mappings")
        return 0
    if args.show_layout:
        for mapping in config.get("mappings", []):
            if isinstance(mapping, dict) and mapping.get("enabled", True):
                requirements = "+".join(mapping.get("requires", []))
                layer = f" [{requirements}]" if requirements else ""
                detail = mapping.get("slot") or mapping.get("parameter") or ""
                print(
                    f"{mapping['device']:>3} {mapping['control']:<28} "
                    f"{mapping['kind']:<8} -> {mapping['action']} {detail}{layer}"
                )
        return 0

    errors = validate_config(config)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        emit("runtime_rejected", reason="invalid-config", errors=errors)
        return 1
    dispatcher = ActionDispatcher(config)
    if args.set_brightness is not None:
        return 0 if dispatcher.set_brightness_percent(args.set_brightness) else 1
    if args.diagnose_display:
        for line in dispatcher.diagnose_displays():
            print(line)
        return 0

    claim_runtime()
    read_only = args.monitor or args.dry_run
    router = EventRouter(config, dry_run=read_only, monitor=read_only)
    mode = "monitor" if args.monitor else "dry-run" if args.dry_run else "active"
    emit(
        "runtime_started",
        pid=os.getpid(),
        mode=mode,
        config=str(args.config or APP_DIR / "config.json"),
        event_log=str(event_path()),
        event_log_mode=log_mode(),
    )
    print(f"MIDIWIN running in {mode} mode. Config: {args.config or APP_DIR / 'config.json'}")
    print(f"Structured event log: {event_path()} ({log_mode()} mode)")
    print("Press Ctrl+C to stop.")
    run_runtime(router.emit)
    return 0
